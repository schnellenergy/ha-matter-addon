# File: chip_tool_server.py
# Enhanced version with clean JSON output and proper parsing

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import logging
import re
from typing import Dict, List, Any, Optional

app = Flask(__name__)
CORS(app)  # Allow all origins

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

CHIP_TOOL_PATH = "/app/connected_home_ip/out/chip-tool-linux/chip-tool"


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes from text"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


class ChipToolOutputParser:
    """Parser for chip-tool output to extract meaningful information"""
    
    @staticmethod
    def parse_attribute_read(stdout: str) -> Dict[str, Any]:
        """Parse attribute read output from chip-tool"""
        # Strip ANSI color codes first
        stdout = strip_ansi_codes(stdout)
        
        result = {
            "attributes": [],
            "success": False,
            "note": None
        }
        
        current_attr = {}
        found_dmg_data = False
        
        for line in stdout.split('\n'):
            # Check for TOO endpoint line to get metadata
            if '[TOO] Endpoint:' in line:
                # Extract endpoint, cluster, attribute
                match = re.search(r'Endpoint:\s+(\d+)\s+Cluster:\s+(0x[0-9A-F_]+)\s+Attribute\s+(0x[0-9A-F_]+)', line)
                if match:
                    current_attr = {
                        'endpoint': int(match.group(1)),
                        'cluster': match.group(2).replace('_', ''),
                        'attribute': match.group(3).replace('_', '')
                    }
                    
                    # Also extract DataVersion if present
                    data_version_match = re.search(r'DataVersion:\s+(\d+)', line)
                    if data_version_match:
                        current_attr['data_version'] = int(data_version_match.group(1))
                    
                    # Mark as successful read (even if we don't have the value)
                    result['success'] = True
            
            # Check for "Don't know how to log" message
            elif "[TOO]   Don't know how to log attribute value" in line:
                if current_attr:
                    current_attr['value'] = None
                    current_attr['type'] = 'unknown'
                    current_attr['note'] = "Value exists but chip-tool cannot display it (custom cluster). Enable DMG logging to see the actual value."
                    result['attributes'].append(current_attr.copy())
                    result['note'] = "DMG logging is not enabled in this chip-tool build. Attribute values for custom clusters cannot be displayed. To fix: rebuild chip-tool with CHIP_PROGRESS_LOGGING=1 or use a build with detailed DMG logging enabled."
                    current_attr = {}
            
            # Parse DMG Data for actual values (this is the key line!)
            elif '[DMG]' in line and 'Data =' in line:
                found_dmg_data = True
                # String values - handle tabs and spaces
                string_match = re.search(r'\[DMG\]\s+Data\s+=\s+"([^"]+)"', line)
                if string_match and current_attr:
                    current_attr['value'] = string_match.group(1)
                    current_attr['type'] = 'string'
                    result['attributes'].append(current_attr.copy())
                    result['success'] = True
                    current_attr = {}
                    continue
                
                # Numeric values
                num_match = re.search(r'\[DMG\]\s+Data\s+=\s+(\d+)', line)
                if num_match and current_attr:
                    current_attr['value'] = int(num_match.group(1))
                    current_attr['type'] = 'integer'
                    result['attributes'].append(current_attr.copy())
                    result['success'] = True
                    current_attr = {}
                    continue
                
                # Boolean values
                bool_match = re.search(r'\[DMG\]\s+Data\s+=\s+(true|false)', line, re.IGNORECASE)
                if bool_match and current_attr:
                    current_attr['value'] = bool_match.group(1).lower() == 'true'
                    current_attr['type'] = 'boolean'
                    result['attributes'].append(current_attr.copy())
                    result['success'] = True
                    current_attr = {}
        
        return result
    
    @staticmethod
    def parse_commissioning(stdout: str) -> Dict[str, Any]:
        """Parse commissioning/pairing output"""
        stdout = strip_ansi_codes(stdout)
        
        result = {
            "success": False,
            "node_id": None,
            "fabric_id": None,
            "stages": []
        }
        
        for line in stdout.split('\n'):
            if '[TOO] Device commissioning completed with success' in line:
                result['success'] = True
            elif '[TOO] Pairing Success' in line:
                result['success'] = True
            elif 'Commissioning complete for node ID' in line:
                match = re.search(r'node ID (0x[0-9A-Fa-f]+)', line)
                if match:
                    result['node_id'] = match.group(1)
            elif 'Fabric ID is' in line:
                match = re.search(r'Fabric ID is (0x[0-9A-Fa-f]+)', line)
                if match:
                    result['fabric_id'] = match.group(1)
            elif 'Successfully finished commissioning step' in line:
                match = re.search(r"step '([^']+)'", line)
                if match:
                    result['stages'].append(match.group(1))
        
        return result
    
    @staticmethod
    def parse_command_response(stdout: str) -> Dict[str, Any]:
        """Parse command response (toggle, on, off, etc.)"""
        stdout = strip_ansi_codes(stdout)
        
        result = {
            "success": False,
            "endpoint": None,
            "cluster": None,
            "command": None
        }
        
        for line in stdout.split('\n'):
            # Look for status report in DMG logs
            if '[DMG]' in line and 'StatusIB' in line:
                result['success'] = True
            elif '[SC] Success status report received' in line:
                result['success'] = True
            elif '[TOO]' in line and 'Endpoint:' in line:
                match = re.search(r'Endpoint:\s+(\d+)', line)
                if match:
                    result['endpoint'] = int(match.group(1))
        
        return result
    
    @staticmethod
    def parse_binding(stdout: str) -> Dict[str, Any]:
        """Parse binding command output"""
        stdout = strip_ansi_codes(stdout)
        
        result = {
            "success": False,
            "message": ""
        }
        
        for line in stdout.split('\n'):
            if '[DMG] WriteClient' in line or '[DMG] WriteResponseMessage' in line:
                result['success'] = True
                result['message'] = "Binding write successful"
                break
            elif '[SC] Success status report received' in line:
                result['success'] = True
                result['message'] = "Binding write successful"
                break
        
        return result


def run_chip_tool(args: List[str]) -> Dict[str, Any]:
    """Execute chip-tool command with proper error handling and parsing"""
    cmd = [CHIP_TOOL_PATH] + args
    logger.info(f"Executing command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        logger.info(f"Command completed with return code: {result.returncode}")

        # Determine command type and parse accordingly
        parsed_data = {}
        if len(args) > 0:
            if args[0] == 'pairing':
                parsed_data = ChipToolOutputParser.parse_commissioning(result.stdout)
            elif args[0] in ['onoff', 'levelcontrol', 'colorcontrol']:
                parsed_data = ChipToolOutputParser.parse_command_response(result.stdout)
            elif args[0] == 'any' and len(args) > 1 and args[1] == 'read-by-id':
                parsed_data = ChipToolOutputParser.parse_attribute_read(result.stdout)
            elif args[0] == 'binding':
                parsed_data = ChipToolOutputParser.parse_binding(result.stdout)
            elif args[0] == 'accesscontrol':
                parsed_data = ChipToolOutputParser.parse_binding(result.stdout)

        # Strip ANSI codes from preview
        clean_stdout = strip_ansi_codes(result.stdout)
        clean_stderr = strip_ansi_codes(result.stderr)

        return {
            "success": result.returncode == 0,
            "command": " ".join(args),
            "returncode": result.returncode,
            "parsed": parsed_data,
            "raw_logs": {
                "stdout_lines": len(clean_stdout.split('\n')),
                "stderr_lines": len(clean_stderr.split('\n')),
                "stdout_preview": clean_stdout[:500] if clean_stdout else "",
                "stderr_preview": clean_stderr[:500] if clean_stderr else ""
            }
        }
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out: {e}")
        return {
            "success": False,
            "error": "Command timed out after 60 seconds",
            "command": " ".join(args)
        }
    except Exception as e:
        logger.error(f"Command failed with exception: {e}")
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(args)
        }


@app.route('/bind', methods=['POST'])
def bind_device():
    """Create binding between two Matter devices"""
    data = request.get_json()
    switch_node = str(data.get('switch_node'))
    switch_endpoint = str(data.get('switch_endpoint', 1))
    light_node = str(data.get('light_node'))
    light_endpoint = str(data.get('light_endpoint', 1))

    if not (switch_node and light_node):
        return jsonify({"error": "Missing switch_node or light_node"}), 400

    # 1. accesscontrol write acl command
    acl_json = (
        '[{"fabricIndex": 1, "privilege": 5, "authMode": 2, "subjects": null, "targets": null}, '
        f'{{"fabricIndex": 1, "privilege": 3, "authMode": 2, "subjects": [{switch_node}], "targets": null}}]'
    )

    acl_result = run_chip_tool([
        "accesscontrol", "write", "acl",
        acl_json,
        light_node,
        "0"
    ])

    # 2. binding write binding command
    binding_json = f'[{{"node":{light_node}, "endpoint":{light_endpoint}, "cluster":6}}]'
    binding_result = run_chip_tool([
        "binding", "write", "binding",
        binding_json,
        switch_node,
        switch_endpoint
    ])

    return jsonify({
        "success": acl_result.get("success") and binding_result.get("success"),
        "acl_command": acl_result,
        "binding_command": binding_result
    })


@app.route('/pair', methods=['POST'])
def pair_device():
    """Commission a Matter device"""
    data = request.get_json()
    node_id = str(data.get('node_id'))
    passcode = str(data.get('passcode'))

    if not node_id or not passcode:
        return jsonify({"error": "Missing node_id or passcode"}), 400

    result = run_chip_tool(["pairing", "code", node_id, passcode])
    return jsonify(result)


@app.route('/command', methods=['POST'])
def run_custom_command():
    """Execute custom chip-tool command"""
    data = request.get_json()

    logger.info(f"Received /command request with data: {data}")

    # Validate request data
    if not data:
        logger.error("No JSON data in request")
        return jsonify({"error": "No JSON data in request body"}), 400

    if 'args' not in data:
        logger.error("Missing 'args' in request body")
        return jsonify({"error": "Missing 'args' in request body"}), 400

    args = data['args']

    # Validate args is a list
    if not isinstance(args, list):
        logger.error(f"'args' is not a list: {type(args)}")
        return jsonify({"error": "'args' must be a list of strings"}), 400

    # Validate all args are strings
    if not all(isinstance(arg, str) for arg in args):
        logger.error(f"Not all args are strings: {args}")
        return jsonify({"error": "'args' must be a list of strings"}), 400

    # Validate args is not empty
    if len(args) == 0:
        logger.error("'args' list is empty")
        return jsonify({"error": "'args' list cannot be empty"}), 400

    logger.info(f"Executing custom command with args: {args}")
    result = run_chip_tool(args)
    return jsonify(result)


@app.route('/toggle', methods=['POST'])
def toggle_device():
    """Toggle a Matter device on/off"""
    data = request.get_json()
    node_id = str(data.get('node_id'))
    endpoint = str(data.get('endpoint', 1))  # default to endpoint 1

    if not node_id:
        return jsonify({"error": "Missing node_id"}), 400

    result = run_chip_tool(["onoff", "toggle", node_id, endpoint])
    return jsonify(result)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "chip-tool-api"})


@app.route('/routes', methods=['GET'])
def list_routes():
    """List all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            "endpoint": rule.endpoint,
            "methods": list(rule.methods),
            "path": str(rule.rule)
        })
    return jsonify({"routes": routes})


if __name__ == '__main__':
    logger.info("Starting chip-tool API server on port 6000")
    logger.info("Available routes:")
    for rule in app.url_map.iter_rules():
        logger.info(f"  {rule.rule} - {list(rule.methods)}")
    app.run(host="0.0.0.0", port=6000, debug=True)
