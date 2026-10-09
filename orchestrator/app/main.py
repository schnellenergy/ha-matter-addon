import os
import time
import json
import sqlite3
import threading
import traceback
import re
import requests
from flask import Flask, render_template, jsonify
from waitress import serve
from datetime import datetime

# Supervisor Configuration
SUPERVISOR_URL = "http://supervisor"

def get_supervisor_token():
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        try:
            with open("/var/run/s6/container_environment/SUPERVISOR_TOKEN", "r") as f:
                token = f.read().strip()
        except Exception:
            pass
    return token

# SQLite Database setup
DB_PATH = "/data/orchestrator.db"

# BigQuery setup (Graceful fallback)
try:
    from google.cloud import bigquery
    # Assumes environment GOOGLE_APPLICATION_CREDENTIALS is set if available
    bq_client = bigquery.Client()
    BQ_ENABLED = True
except Exception:
    bq_client = None
    BQ_ENABLED = False

# Flask App
app = Flask(__name__)

# Addons to manage by their base slugs (ignoring repository prefixes like 'local_')
BOOT_SEQUENCE_BASES = [
    ["openthread_border_router"], # Step 1: OpenThread
    ["matter_server"],            # Step 2: Matter Server
    ["custom_data_storage", "ha_data_catcher", "smash_wifi_onboarding"] # Step 3: Custom Addons
]

MONITORED_ADDONS = {}

def resolve_slug(base_slug, all_addons):
    """Finds the actual full slug (e.g., local_ha_data_catcher) from the base name."""
    for addon in all_addons:
        if addon.get('slug', '').endswith(base_slug):
            return addon['slug']
    # Fallback to base_slug if not found
    return base_slug

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS addon_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            addon_slug TEXT,
            event_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            details TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_event(addon_slug, event_type, reason="", details=""):
    print(f"[{addon_slug}] {event_type} - {reason}")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO addon_logs (addon_slug, event_type, reason, details) VALUES (?, ?, ?, ?)',
                  (addon_slug, event_type, reason, details))
        conn.commit()
        conn.close()
        
        # Push to BigQuery if enabled
        if BQ_ENABLED:
            with open("/data/options.json") as f:
                options = json.load(f)
            dataset = options.get("bigquery_dataset", "schnell_telemetry")
            table = options.get("bigquery_table", "addon_lifecycle_logs")
            if dataset and table:
                table_id = f"{bq_client.project}.{dataset}.{table}"
                rows_to_insert = [
                    {"addon_slug": addon_slug, "event_type": event_type, "timestamp": datetime.utcnow().isoformat(), "reason": reason, "details": details}
                ]
                bq_client.insert_rows_json(table_id, rows_to_insert)
    except Exception as e:
        print(f"Failed to log event: {e}")

class SupervisorClient:
    def get_headers(self):
        token = get_supervisor_token()
        if not token:
            print("WARNING: SUPERVISOR_TOKEN is empty! API calls will fail with 401.")
        return {"Authorization": f"Bearer {token}"}
        
    def _request(self, method, endpoint, **kwargs):
        url = f"{SUPERVISOR_URL}{endpoint}"
        try:
            res = requests.request(method, url, headers=self.get_headers(), timeout=10, **kwargs)
            res.raise_for_status()
            return res.json().get('data', {})
        except Exception as e:
            print(f"Supervisor API Error on {endpoint}: {e}")
            return None

    def get_all_addons(self):
        data = self._request("GET", "/addons")
        return data.get('addons', []) if data else []

    def get_addon_info(self, slug):
        return self._request("GET", f"/addons/{slug}/info")

    def get_addon_logs(self, slug):
        # We use a raw request here to get text, not JSON
        url = f"{SUPERVISOR_URL}/addons/{slug}/logs"
        try:
            res = requests.get(url, headers=self.get_headers(), timeout=10)
            res.raise_for_status()
            return res.text
        except Exception as e:
            print(f"Failed to get logs for {slug}: {e}")
            return ""

    def start_addon(self, slug):
        return self._request("POST", f"/addons/{slug}/start")
        
    def stop_addon(self, slug):
        return self._request("POST", f"/addons/{slug}/stop")

supervisor = SupervisorClient()

class Orchestrator:
    def __init__(self):
        self.known_states = {}
        self.crash_history = {} # Track crash timestamps {slug: [timestamps]}

    def run_boot_sequence(self):
        print("Starting Boot Sequence...")
        all_addons = supervisor.get_all_addons()
        
        for step, group_bases in enumerate(BOOT_SEQUENCE_BASES):
            # Resolve real slugs for this group
            group = [resolve_slug(base, all_addons) for base in group_bases]
            
            print(f"Boot Step {step + 1}: Starting {group}")
            for slug in group:
                info = supervisor.get_addon_info(slug)
                if info and info.get('state') != 'started':
                    print(f"Starting {slug}...")
                    supervisor.start_addon(slug)
                    log_event(slug, "BOOT_START")
            
            # Wait for all in group to be started
            for slug in group:
                wait_count = 0
                while True:
                    info = supervisor.get_addon_info(slug)
                    state = info.get('state') if info else 'unknown'
                    if state == 'started':
                        print(f"{slug} is started.")
                        self.known_states[slug] = 'started'
                        break
                    print(f"Waiting for {slug} to start... (Current state: {state})")
                    time.sleep(5)
                    wait_count += 1
                    if wait_count > 12: # 1 min timeout per addon boot
                        print(f"Timeout waiting for {slug} to boot.")
                        break

    def analyze_logs(self, slug):
        logs = supervisor.get_addon_logs(slug)
        if not logs:
            return "UNKNOWN", "No logs available"
            
        last_lines = "\n".join(logs.splitlines()[-100:])
        
        # Categorize Error
        if re.search(r'(database disk image is malformed|database is locked|sqlite3\.DatabaseError)', last_lines, re.IGNORECASE):
            return "DB_CORRUPTION", last_lines
        if re.search(r'(CHIP Error|Radio disconnected|No Thread network|Failed to start Matter|CHIP_ERROR_TIMEOUT|Matter server connection lost)', last_lines, re.IGNORECASE):
            return "MATTER_NETWORK_ERROR", last_lines
        if re.search(r'(ttyUSB|ttyACM|No such file or directory: \'/dev/|Failed to open serial port|USB disconnect)', last_lines, re.IGNORECASE):
            return "HARDWARE_DISCONNECT", last_lines
        if re.search(r'(MemoryError|Out of memory|code 137|Killed)', last_lines, re.IGNORECASE):
            return "OOM_CRASH", last_lines
        if re.search(r'(Configuration invalid|YAML error|KeyError|voluptuous\.error|yaml\.parser)', last_lines, re.IGNORECASE):
            return "CONFIG_ERROR", last_lines
        if re.search(r'(SyntaxError|ModuleNotFoundError|ImportError|IndentationError)', last_lines, re.IGNORECASE):
            return "CODE_BUG", last_lines
        if re.search(r'(TimeoutError|ConnectionRefusedError|socket\.error|Cannot connect to host)', last_lines, re.IGNORECASE):
            return "NETWORK_ERROR", last_lines
            
        # Ignore graceful SystemExits that throw Tracebacks
        if re.search(r'Traceback', last_lines, re.IGNORECASE):
            if not re.search(r'(SystemExit: 0|SIGTERM)', last_lines, re.IGNORECASE):
                return "TRANSIENT_EXCEPTION", last_lines
            
        return "CRASH", last_lines

    def solve_and_recover(self, slug, category, details):
        if category == "CONFIG_ERROR":
            print(f"[{slug}] Configuration error detected. Restarting to see if it clears...")
            time.sleep(2)
            
        elif category == "MATTER_NETWORK_ERROR":
            print(f"[{slug}] Matter/Thread failure detected. Restarting OpenThread Router first...")
            supervisor.start_addon("core_openthread_border_router")
            time.sleep(10) # Give router a head start

        elif category == "OOM_CRASH":
            print(f"[{slug}] Out of memory. Waiting 60s for OS to cleanup before restart...")
            time.sleep(60)
            
        elif category == "HARDWARE_DISCONNECT":
            print(f"[{slug}] Hardware disconnect. Waiting 10s for USB remount...")
            time.sleep(10)
            
        # Check crash loop guard
        now = time.time()
        if slug not in self.crash_history:
            self.crash_history[slug] = []
        
        # Prune crashes older than 2 minutes
        self.crash_history[slug] = [t for t in self.crash_history[slug] if now - t < 120]
        self.crash_history[slug].append(now)
        
        crash_count = len(self.crash_history[slug])
        if crash_count >= 5:
            print(f"[{slug}] CRASH LOOP GUARD: {crash_count} crashes in 2 mins. Cooling down for 30s...")
            log_event(slug, "COOLDOWN", f"Crash loop detected ({crash_count} crashes).")
            time.sleep(30)

        print(f"[{slug}] Attempting auto-recovery (instant)...")
        supervisor.start_addon(slug)
        log_event(slug, "Auto Recovery Attempted", "Re-started")

    def monitor_loop(self):
        print("Entering Monitor Loop...")
        while True:
            try:
                all_addons = supervisor.get_all_addons()
                # Build a flattened list of all monitored real slugs
                monitored_slugs = []
                for group in BOOT_SEQUENCE_BASES:
                    for base in group:
                        monitored_slugs.append(resolve_slug(base, all_addons))
                        
                for addon in all_addons:
                    slug = addon['slug']
                    state = addon['state']
                    
                    if slug not in monitored_slugs:
                        continue
                    last_state = self.known_states.get(slug, state)
                    
                    # ANY STOP IS A CRASH IN CONSUMER MODE!
                    if last_state != state and state in ['stopped', 'error']:
                        # CRASH DETECTED
                        log_event(slug, "Crash Detected", state.capitalize())
                        time.sleep(1)
                        
                        category, details = self.analyze_logs(slug)
                        log_event(slug, "Analysis Completed", "Crash")
                        time.sleep(1)
                        
                        self.solve_and_recover(slug, category, details)
                    
                    self.known_states[slug] = state
                    
            except Exception as e:
                print(f"Error in monitor loop: {e}")
                traceback.print_exc()
            
            time.sleep(30)

orchestrator = Orchestrator()

# --- Flask Web UI ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    addons = supervisor.get_all_addons()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT addon_slug, event_type, timestamp, reason FROM addon_logs ORDER BY id DESC LIMIT 500')
    logs = [{"slug": row[0], "event": row[1], "time": row[2], "reason": row[3]} for row in c.fetchall()]
    conn.close()
    
    status_data = []
    if addons:
        monitored_slugs = []
        for group in BOOT_SEQUENCE_BASES:
            for base in group:
                monitored_slugs.append(resolve_slug(base, addons))

        for a in addons:
            if a.get("slug") not in monitored_slugs:
                continue
            status_data.append({
                "name": a.get("name"),
                "slug": a.get("slug"),
                "state": a.get("state"),
                "version": a.get("version"),
                "description": a.get("description", "No description provided."),
                "update_available": a.get("update_available")
            })
            
    return jsonify({
        "addons": status_data,
        "logs": logs
    })

def start_flask():
    print("Starting Flask Web UI on port 8099...")
    serve(app, host='0.0.0.0', port=8099)

def main():
    print("Initialize Database...")
    init_db()
    
    print("Starting Web UI Thread...")
    ui_thread = threading.Thread(target=start_flask, daemon=True)
    ui_thread.start()
    
    print("Waiting for Supervisor to be fully ready...")
    time.sleep(10)

    # Outer loop ensuring Orchestrator NEVER dies
    while True:
        try:
            orchestrator.run_boot_sequence()
            orchestrator.monitor_loop()
        except Exception as e:
            print(f"FATAL ORCHESTRATOR ERROR: {e}")
            traceback.print_exc()
            log_event("orchestrator", "SELF_RECOVERY", "Watchdog crashed, restarting loop", str(e))
            time.sleep(15)

if __name__ == '__main__':
    main()
