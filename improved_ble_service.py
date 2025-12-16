#!/usr/bin/env python3
"""
Improved SMASH BLE Service with proper D-Bus integration for Home Assistant OS
"""

import os
import sys
import logging
import subprocess
import time
import signal
import json
import re
import threading
import traceback
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import Firestore helper for IP management
try:
    from firestore_helper import FirestoreHelper
    FIRESTORE_AVAILABLE = True
    logger.info('✅ Firestore helper imported successfully')
except ImportError as e:
    logger.warning(f'⚠️ Firestore helper not available: {e}')
    FIRESTORE_AVAILABLE = False

def get_mac_address():
    """Get the MAC address of the Raspberry Pi's primary network interface"""
    try:
        # Try to get MAC from wlan0 first (WiFi interface)
        result = subprocess.run(['cat', '/sys/class/net/wlan0/address'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            mac = result.stdout.strip().upper()
            logger.info(f'📍 MAC Address (wlan0): {mac}')
            return mac
        
        # Fallback to eth0/end0 (Ethernet interface)
        for interface in ['eth0', 'end0']:
            result = subprocess.run(['cat', f'/sys/class/net/{interface}/address'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                mac = result.stdout.strip().upper()
                logger.info(f'📍 MAC Address ({interface}): {mac}')
                return mac
        
        logger.error('❌ Could not get MAC address from any interface')
        return None
    except Exception as e:
        logger.error(f'❌ Error getting MAC address: {e}')
        return None


def set_led_status(status: str):
    """Helper function to control the LED by writing to a status file."""
    try:
        # Validate status before setting
        valid_statuses = [
            'booting', 'error', 'factory_reset', 'ethernet_connected', 
            'wifi_connected', 'wifi_connecting', 'ble_advertising', 
            'setup_in_progress', 'wifi_no_internet', 'ethernet_no_internet', 
            'internet_connected', 'dual_network', 'shutdown'
        ]
        
        if status not in valid_statuses:
            logger.error(f"🚥 INVALID LED STATUS: '{status}' - using 'error' instead")
            status = 'error'
        
        with open("/tmp/led_status", 'w') as f:
            f.write(status)
        logger.info(f"🚥 LED status set to: {status}")
    except Exception as e:
        logger.error(f"Failed to write LED status: {e}")

def _configure_home_assistant_ethernet_access(eth_status):
    """CRITICAL FIX: Configure Home Assistant to bind to new Ethernet IP immediately"""
    try:
        eth_ip = eth_status['ip']
        eth_interface = eth_status['interface'] or 'end0'

        if not eth_ip:
            logger.warning("⚠️ No Ethernet IP available for Home Assistant configuration")
            return False

        logger.info(f"🔧 CRITICAL FIX: Configuring Home Assistant for immediate Ethernet access at {eth_ip}:8123")

        # Method 1: Force Home Assistant to rebind to all interfaces
        logger.info("🔧 Method 1: Attempting Home Assistant service restart to rebind to new IP...")
        try:
            # Try to restart Home Assistant core via supervisor API
            restart_result = subprocess.run([
                "curl", "-X", "POST",
                "-H", "Authorization: Bearer $SUPERVISOR_TOKEN",
                "-H", "Content-Type: application/json",
                "http://supervisor/core/restart"
            ], capture_output=True, text=True, timeout=10)

            if restart_result.returncode == 0:
                logger.info("✅ Home Assistant restart initiated - will rebind to all IPs in 30 seconds")
                # Give Home Assistant time to restart and rebind
                time.sleep(5)  # Short wait for restart to begin
                return True
            else:
                logger.info("ℹ️ Home Assistant restart via supervisor not available")
        except Exception as e:
            logger.info(f"ℹ️ Home Assistant restart not available: {e}")

        # Method 1.5: Try alternative Home Assistant restart methods
        logger.info("🔧 Method 1.5: Trying alternative Home Assistant restart methods...")
        try:
            # Try systemctl restart (if available)
            systemctl_result = subprocess.run([
                "systemctl", "restart", "homeassistant"
            ], capture_output=True, text=True, timeout=10)

            if systemctl_result.returncode == 0:
                logger.info("✅ Home Assistant restarted via systemctl")
                time.sleep(5)
                return True
            else:
                logger.info("ℹ️ systemctl restart not available")

        except Exception as e:
            logger.info(f"ℹ️ systemctl restart not available: {e}")

        # Try supervisor addon restart
        try:
            supervisor_restart = subprocess.run([
                "curl", "-X", "POST",
                "-H", "Authorization: Bearer $SUPERVISOR_TOKEN",
                "http://supervisor/addons/core_homeassistant/restart"
            ], capture_output=True, text=True, timeout=10)

            if supervisor_restart.returncode == 0:
                logger.info("✅ Home Assistant restarted via supervisor addon API")
                time.sleep(5)
                return True
            else:
                logger.info("ℹ️ supervisor addon restart not available")

        except Exception as e:
            logger.info(f"ℹ️ supervisor addon restart not available: {e}")

        # Method 2: Force Home Assistant to bind to all interfaces
        logger.info("🔧 Method 2: Configuring Home Assistant to bind to all interfaces...")
        try:
            # Create/update Home Assistant network configuration
            ha_config_dir = "/config"
            if not os.path.exists(ha_config_dir):
                ha_config_dir = "/data/homeassistant"  # Alternative path

            if os.path.exists(ha_config_dir):
                config_file = os.path.join(ha_config_dir, "configuration.yaml")

                # Read existing config
                config_content = ""
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        config_content = f.read()

                # Check if http config exists
                if "http:" not in config_content:
                    # Add http configuration to bind to all interfaces
                    http_config = """
# Network configuration for dual interface access
http:
  server_host: 0.0.0.0
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1
    - ::1
    - 192.168.0.0/16
    - 172.16.0.0/12
    - 10.0.0.0/8
"""
                    with open(config_file, 'a') as f:
                        f.write(http_config)

                    logger.info("✅ Home Assistant configuration updated to bind to all interfaces")
                else:
                    logger.info("ℹ️ Home Assistant http config already exists")

            # Force network interface refresh
            subprocess.run(["ip", "link", "set", eth_interface, "down"], capture_output=True)
            time.sleep(1)
            subprocess.run(["ip", "link", "set", eth_interface, "up"], capture_output=True)
            time.sleep(2)

            # Verify IP is still assigned after interface refresh
            ip_check = subprocess.run(["ip", "addr", "show", eth_interface], capture_output=True, text=True)
            if eth_ip in ip_check.stdout:
                logger.info(f"✅ Ethernet IP {eth_ip} confirmed after interface refresh")
            else:
                logger.warning(f"⚠️ Ethernet IP {eth_ip} lost after interface refresh")
                return False

        except Exception as e:
            logger.warning(f"⚠️ Interface refresh failed: {e}")

        # Method 3: Configure network routing to force Home Assistant binding
        logger.info("🔧 Method 3: Configuring advanced routing for Home Assistant binding...")
        try:
            # Add specific routes that force Home Assistant to recognize the new IP
            subprocess.run([
                "ip", "route", "add", f"{eth_ip}/32", "dev", eth_interface, "scope", "host"
            ], capture_output=True)

            # Add local route for the Ethernet subnet
            eth_subnet = f"{'.'.join(eth_ip.split('.')[:-1])}.0/24"
            subprocess.run([
                "ip", "route", "add", eth_subnet, "dev", eth_interface, "scope", "link"
            ], capture_output=True)

            logger.info(f"✅ Advanced routing configured for {eth_ip}")

        except Exception as e:
            logger.warning(f"⚠️ Advanced routing configuration failed: {e}")

        # Method 4: Test and verify Home Assistant accessibility
        logger.info("🔧 Method 4: Testing Home Assistant accessibility on Ethernet IP...")
        max_attempts = 6  # Test for 30 seconds (6 attempts x 5 seconds)

        for attempt in range(max_attempts):
            try:
                # Test if Home Assistant is listening on the Ethernet IP
                import socket
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(3)
                result = test_socket.connect_ex((eth_ip, 8123))
                test_socket.close()

                if result == 0:
                    logger.info(f"✅ SUCCESS: Home Assistant is now accessible at http://{eth_ip}:8123")
                    return True
                else:
                    logger.info(f"⏳ Attempt {attempt + 1}/{max_attempts}: Home Assistant not yet accessible on {eth_ip}:8123")
                    if attempt < max_attempts - 1:  # Don't sleep on last attempt
                        time.sleep(5)

            except Exception as e:
                logger.info(f"⏳ Attempt {attempt + 1}/{max_attempts}: Connection test failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(5)

        # If we get here, Home Assistant is not accessible on the Ethernet IP
        logger.error(f"❌ CRITICAL: Home Assistant is not accessible on Ethernet IP {eth_ip}:8123 after all attempts")
        logger.error("❌ This indicates Home Assistant is not binding to the new Ethernet IP address")

        # Final diagnostic: Check what IPs Home Assistant is actually bound to
        try:
            netstat_result = subprocess.run([
                "netstat", "-tlnp"
            ], capture_output=True, text=True)

            ha_bindings = []
            for line in netstat_result.stdout.split('\n'):
                if ':8123' in line:
                    ha_bindings.append(line.strip())

            if ha_bindings:
                logger.error("❌ Home Assistant is currently bound to:")
                for binding in ha_bindings:
                    logger.error(f"   {binding}")
                logger.error(f"❌ But NOT bound to {eth_ip}:8123")
            else:
                logger.error("❌ Home Assistant is not listening on port 8123 at all!")

        except Exception as e:
            logger.error(f"❌ Failed to check Home Assistant bindings: {e}")

        return False

    except Exception as e:
        logger.error(f"❌ Failed to configure Home Assistant Ethernet access: {e}")
        return False

def _setup_basic_ethernet_access(eth_status):
    """Setup basic Ethernet access when WiFi is not connected"""
    try:
        eth_interface = eth_status['interface'] or 'end0'
        eth_ip = eth_status['ip']

        if not eth_ip:
            logger.warning("⚠️ No Ethernet IP available for basic setup")
            return

        logger.info(f"🔧 Setting up basic Ethernet access for {eth_ip}")

        # Ensure interface is up
        subprocess.run(["ip", "link", "set", eth_interface, "up"], capture_output=True)

        # Add subnet route for Ethernet
        subprocess.run([
            "ip", "route", "add", f"{eth_ip}/24", "dev", eth_interface, "scope", "link", "src", eth_ip
        ], capture_output=True)

        # Add host route for Home Assistant access
        subprocess.run([
            "ip", "route", "add", f"{eth_ip}/32", "dev", eth_interface
        ], capture_output=True)

        # Derive and set default gateway
        ip_parts = eth_ip.split('.')
        eth_gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"

        subprocess.run([
            "ip", "route", "add", "default", "via", eth_gateway, "dev", eth_interface
        ], capture_output=True)

        logger.info(f"✅ Basic Ethernet access configured: http://{eth_ip}:8123")

        # CRITICAL FIX: Also configure Home Assistant for this IP
        _configure_home_assistant_ethernet_access(eth_status)

    except Exception as e:
        logger.error(f"❌ Failed to setup basic Ethernet access: {e}")

def update_network_led_status():
    """
    SIMPLIFIED LED status based on network connection only (NO internet detection)
    Priority: Ethernet > WiFi > No connection (blinking red)

    LED Behavior Rules:
    - Ethernet connected: Solid GREEN (highest priority)
    - WiFi connected (no Ethernet): Solid BLUE
    - No network connection: Blinking RED (ready for WiFi setup via BLE)
    """
    try:
        # Rate limiting for network status updates (INSTANT transitions)
        import time
        current_time = time.time()
        if hasattr(update_network_led_status, 'last_call_time'):
            if current_time - update_network_led_status.last_call_time < 0.05:  # 0.05 second for INSTANT response
                logger.debug("🚥 Network LED update rate limited (< 0.05s since last call)")
                return
        update_network_led_status.last_call_time = current_time
        
        # Check Ethernet status - SIMPLE connection detection only
        eth_connected = False

        for interface in ['eth0', 'end0']:
            try:
                eth_check = subprocess.run(['ip', 'addr', 'show', interface], capture_output=True, text=True)
                if eth_check.returncode == 0 and 'inet ' in eth_check.stdout:
                    eth_connected = True
                    logger.debug(f"🔍 Ethernet {interface} connected with IP")
                    break
            except Exception:
                continue
        
        # Check WiFi status - SIMPLE connection detection only
        wifi_connected = False

        try:
            wifi_check = subprocess.run(['ip', 'addr', 'show', 'wlan0'], capture_output=True, text=True)
            if wifi_check.returncode == 0 and 'inet ' in wifi_check.stdout:
                # Additional check: Ensure WiFi is actually connected to a network
                wifi_status = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True)
                if 'ESSID:' in wifi_status.stdout and 'ESSID:off' not in wifi_status.stdout:
                    wifi_connected = True
                    logger.debug(f"🔍 WiFi wlan0 connected to network with IP")
                else:
                    logger.debug(f"🔍 WiFi wlan0 has IP but not connected to network (ESSID:off)")
            else:
                logger.debug(f"🔍 WiFi wlan0 interface: no IP address")
        except Exception as e:
            logger.debug(f"🔍 WiFi check exception: {e}")
        
        # Log current network state - SIMPLIFIED
        logger.info(f"🔍 Network status check: Ethernet={eth_connected}, WiFi={wifi_connected}")

        # SIMPLIFIED LED status based on connection only (NO internet detection)
        if eth_connected:
            # Ethernet connected - ALWAYS solid green (highest priority)
            set_led_status('ethernet_connected')  # Solid green
            logger.info("🚥 LED: Solid GREEN (Ethernet connected)")
        elif wifi_connected:
            # WiFi connected, no Ethernet - ALWAYS solid blue
            set_led_status('wifi_connected')  # Solid blue
            logger.info("🚥 LED: Solid BLUE (WiFi connected, no Ethernet)")
        else:
            # No network connection - check if we're in auto-reconnection mode
            auto_reconnect = os.getenv('WIFI_AUTO_RECONNECT', 'false').lower() == 'true'

            if auto_reconnect:
                # During auto-reconnection, don't override the wifi_connecting status
                # Only set to booting if we're not currently trying to reconnect
                try:
                    with open("/tmp/led_status", 'r') as f:
                        current_status = f.read().strip()

                    if current_status == 'wifi_connecting':
                        # Don't override - let the reconnection process manage the LED
                        logger.debug("🚥 LED: Maintaining SOLID RED (Wi-Fi reconnection in progress)")
                        return
                except:
                    pass

            # No network connection - blinking red (ready for WiFi setup)
            set_led_status('booting')  # Blinking red - no network, ready for setup
            logger.info("🚥 LED: Blinking RED (No network - ready for WiFi setup via BLE)")
            
    except Exception as e:
        logger.error(f"Error updating LED status: {e}")
        # Default to blinking red if there's an error
        set_led_status('booting')  # Blinking red

# Try to import D-Bus libraries with error handling
try:
    # First try system packages
    import sys
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    sys.path.insert(0, '/usr/lib/python3.11/dist-packages')
    
    import dbus
    import dbus.exceptions
    import dbus.mainloop.glib
    import dbus.service
    from gi.repository import GLib
    DBUS_AVAILABLE = True
    logger.info("✅ D-Bus libraries loaded successfully (system packages)")
except ImportError as e1:
    logger.warning(f"⚠️ System D-Bus packages failed: {e1}")
    try:
        # Fallback to pip packages
        import dbus
        import dbus.exceptions  
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
        DBUS_AVAILABLE = True
        logger.info("✅ D-Bus libraries loaded successfully (pip packages)")
    except ImportError as e2:
        logger.error(f"❌ Failed to import D-Bus libraries (system: {e1}, pip: {e2})")
        DBUS_AVAILABLE = False

class WiFiController:
    """Enhanced WiFi controller with proper network management and LED status integration"""
    
    def __init__(self):
        self.config_path = "/data/wifi_config.json"
        self.wpa_conf_path = "/tmp/wpa_supplicant.conf"

    def get_available_networks(self) -> List[Dict[str, str]]:
        """Get list of available WiFi networks with signal strength"""
        try:
            # First bring up the interface
            subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)
            time.sleep(2)
            
            # Scan for networks
            result = subprocess.run(["iwlist", "wlan0", "scan"], capture_output=True, text=True)
            networks = []
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                current_network = {}
                
                for line in lines:
                    line = line.strip()
                    if 'Cell' in line and 'Address:' in line:
                        if current_network.get('ssid'):
                            networks.append(current_network)
                        current_network = {}
                        # Extract MAC address
                        mac = line.split('Address: ')[1].strip() if 'Address: ' in line else ""
                        current_network['bssid'] = mac
                    elif 'ESSID:' in line:
                        essid_match = re.search(r'ESSID:\"([^\"]*)\"', line)
                        if essid_match:
                            essid = essid_match.group(1)
                            if essid and essid != '<hidden>':
                                current_network['ssid'] = essid
                    elif 'Quality=' in line:
                        quality_match = re.search(r'Signal level=(-?\d+)', line)
                        if quality_match:
                            signal_level = int(quality_match.group(1))
                            current_network['signal_strength'] = signal_level
                        else:
                            # Fallback parsing
                            quality_part = line.split('Quality=')[1].split()[0] if 'Quality=' in line else "0/70"
                            current_network['quality'] = quality_part
                
                if current_network.get('ssid'):
                    networks.append(current_network)
            
            # Remove duplicates and sort by signal strength
            unique_networks = {}
            for net in networks:
                ssid = net.get('ssid')
                if ssid and ssid not in unique_networks:
                    unique_networks[ssid] = net
            
            final_networks = list(unique_networks.values())
            final_networks.sort(key=lambda x: x.get('signal_strength', -100), reverse=True)
            
            logger.info(f"📡 Found {len(final_networks)} unique WiFi networks")
            for net in final_networks[:3]:  # Log top 3
                logger.info(f"  - {net['ssid']}: {net.get('signal_strength', 'unknown')} dBm")
            
            return final_networks
            
        except Exception as e:
            logger.error(f"Failed to scan WiFi networks: {e}")
            return []

    def _store_ethernet_ip(self, ip_address):
        """Store the current Ethernet IP for reference (Home Assistant OS manages networking)"""
        try:
            with open("/tmp/ethernet_ip", 'w') as f:
                f.write(ip_address)
            logger.info(f"📝 Stored Ethernet IP for reference: {ip_address}")
        except Exception as e:
            logger.error(f"❌ Failed to store Ethernet IP: {e}")

    def _get_stored_ethernet_ip(self):
        """Get the previously stored Ethernet IP for reference"""
        try:
            if os.path.exists("/tmp/ethernet_ip"):
                with open("/tmp/ethernet_ip", 'r') as f:
                    stored_ip = f.read().strip()
                logger.info(f"📖 Retrieved stored Ethernet IP: {stored_ip}")
                return stored_ip
        except Exception as e:
            logger.error(f"❌ Failed to read stored Ethernet IP: {e}")
        return None

    def _check_ethernet_connection(self):
        """Check if Ethernet is connected and return interface name and IP"""
        eth_interfaces = ['eth0', 'end0']

        for interface in eth_interfaces:
            try:
                eth_check = subprocess.run(['ip', 'addr', 'show', interface], capture_output=True, text=True)
                if eth_check.returncode == 0:
                    interface_status = eth_check.stdout
                    
                    # Check if interface is UP and has IP
                    is_up = 'state UP' in interface_status or 'UP' in interface_status
                    has_ip = 'inet ' in interface_status
                    
                    if is_up and has_ip:
                        # Extract current IP address
                        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', interface_status)
                        current_ip = ip_match.group(1) if ip_match else None
                        
                        if current_ip:
                            # Store the current IP for reference only (don't try to restore)
                            self._store_ethernet_ip(current_ip)
                            logger.info(f"📡 Ethernet detected on {interface}: {current_ip}")
                            return {'connected': True, 'interface': interface, 'ip': current_ip}
                    
                    elif is_up and not has_ip:
                        # Interface is up but no IP yet, might be getting DHCP
                        logger.info(f"🔍 Ethernet {interface} is up but waiting for IP...")
                        return {'connected': False, 'interface': interface, 'ip': None}
                        
            except Exception as e:
                logger.debug(f"Error checking {interface}: {e}")
                continue

        logger.info("🔍 No Ethernet detected on eth0 or end0")
        return {'connected': False, 'interface': None, 'ip': None}

    def _setup_dual_network_routing(self, wifi_ip, wifi_gateway, is_static=True):
        """REFERENCE IMPLEMENTATION: Simple priority-based routing for dual network access"""
        logger.info("🌐 Setting up dual network access using REFERENCE IMPLEMENTATION approach...")

        # Check if Ethernet is connected
        eth_status = self._check_ethernet_connection()
        has_ethernet = eth_status['connected']

        if not has_ethernet:
            logger.info("🔧 WiFi-only setup - ensuring immediate Home Assistant access")

            # Simple WiFi-only routing
            subprocess.run(["ip", "route", "del", "default"], capture_output=True)
            time.sleep(1)

            # Ensure WiFi interface is up
            subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)

            # CRITICAL FIX: Add subnet route first to ensure local network access
            wifi_subnet = '.'.join(wifi_ip.split('.')[:-1]) + '.0/24'
            subprocess.run([
                "ip", "route", "add", wifi_subnet, "dev", "wlan0", "scope", "link"
            ], capture_output=True)

            # Add default route via WiFi
            subprocess.run([
                "ip", "route", "add", "default", "via", wifi_gateway, "dev", "wlan0"
            ], capture_output=True)

            # CRITICAL FIX: Add explicit host route for the WiFi IP
            subprocess.run([
                "ip", "route", "add", f"{wifi_ip}/32", "dev", "wlan0", "scope", "host"
            ], capture_output=True)

            logger.info(f"✅ WiFi Home Assistant IMMEDIATELY accessible at: http://{wifi_ip}:8123")
            logger.info(f"✅ WiFi subnet route added: {wifi_subnet}")
            logger.info(f"✅ WiFi host route added: {wifi_ip}/32")

        else:
            # REFERENCE IMPLEMENTATION: Simple dual network with Ethernet priority
            eth_ip = eth_status['ip']
            eth_interface = eth_status['interface'] or 'end0'

            logger.info(f"🌐 REFERENCE DUAL SETUP: WiFi {wifi_ip} + Ethernet {eth_ip}")
            logger.info("🔧 Using REFERENCE IMPLEMENTATION approach for dual network routing...")

            # Ensure both interfaces are up
            subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)
            subprocess.run(["ip", "link", "set", eth_interface, "up"], capture_output=True)

            # Detect Ethernet gateway (reference implementation approach)
            eth_gateway = None
            try:
                # Try to detect gateway from existing routes
                route_check = subprocess.run(["ip", "route", "show", "dev", eth_interface], capture_output=True, text=True)
                for line in route_check.stdout.split('\n'):
                    if 'default' in line and 'via' in line:
                        parts = line.split()
                        if 'via' in parts:
                            gateway_idx = parts.index('via') + 1
                            if gateway_idx < len(parts):
                                eth_gateway = parts[gateway_idx]
                                break

                # If no gateway found, derive from IP (reference approach)
                if not eth_gateway and eth_ip:
                    ip_parts = eth_ip.split('.')
                    eth_gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"
                    logger.info(f"🔧 Derived Ethernet gateway: {eth_gateway}")

            except Exception as e:
                logger.warning(f"⚠️ Gateway detection failed: {e}")
                if eth_ip:
                    ip_parts = eth_ip.split('.')
                    eth_gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"

            # REFERENCE IMPLEMENTATION: Simple priority-based routing
            logger.info("🛣️ REFERENCE: Setting up priority-based routing (Ethernet > WiFi)")

            # Step 1: CRITICAL FIX - Preserve WiFi routes before removing defaults
            logger.info("🔧 CRITICAL FIX: Preserving WiFi accessibility during route changes...")

            # First, ensure WiFi subnet route exists before removing defaults
            wifi_subnet = '.'.join(wifi_ip.split('.')[:-1]) + '.0/24'
            subprocess.run([
                "ip", "route", "add", wifi_subnet, "dev", "wlan0", "scope", "link", "metric", "200"
            ], capture_output=True)

            # Add WiFi host route to ensure IP remains accessible
            subprocess.run([
                "ip", "route", "add", f"{wifi_ip}/32", "dev", "wlan0", "scope", "host"
            ], capture_output=True)

            # Now remove default routes (but preserve subnet routes)
            subprocess.run(["ip", "route", "del", "default"], capture_output=True)
            time.sleep(1)

            # Step 2: Add Ethernet as primary default route (reference approach)
            if eth_gateway and eth_ip:
                result = subprocess.run([
                    "ip", "route", "add", "default", "via", eth_gateway,
                    "dev", eth_interface, "metric", "100"
                ], capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info(f"✅ REFERENCE: Ethernet default route set: {eth_interface} via {eth_gateway}")
                else:
                    logger.warning(f"⚠️ Failed to set ethernet default route: {result.stderr}")

            # Step 3: Add WiFi as backup route (reference approach)
            result = subprocess.run([
                "ip", "route", "add", "default", "via", wifi_gateway,
                "dev", "wlan0", "metric", "200"
            ], capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"✅ REFERENCE: WiFi backup route added: wlan0 via {wifi_gateway} (lower priority)")
            else:
                logger.info(f"ℹ️ WiFi backup route: {result.stderr}")

            # Step 4: Show final network status (reference approach)
            logger.info("📊 REFERENCE: Final network configuration:")
            route_result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
            if route_result.returncode == 0:
                routes = route_result.stdout.strip()
                logger.info(f"   Active routes: {len(routes.split(chr(10)))} routes configured")
                # Log first few routes for debugging
                for i, route in enumerate(routes.split('\n')[:3]):
                    if route.strip():
                        logger.info(f"   Route {i+1}: {route.strip()}")

            # Step 5: CRITICAL FIX - Add explicit routes to ensure BOTH IPs remain accessible
            logger.info("🔧 CRITICAL FIX: Adding explicit routes for BOTH WiFi and Ethernet accessibility...")

            # CRITICAL: Add specific subnet routes to ensure local access to both networks
            wifi_subnet = '.'.join(wifi_ip.split('.')[:-1]) + '.0/24'
            eth_subnet = '.'.join(eth_ip.split('.')[:-1]) + '.0/24' if eth_ip else None

            # Add WiFi subnet route with higher metric (backup)
            wifi_subnet_result = subprocess.run([
                "ip", "route", "add", wifi_subnet, "dev", "wlan0", "scope", "link", "metric", "200"
            ], capture_output=True, text=True)

            if wifi_subnet_result.returncode == 0:
                logger.info(f"✅ WiFi subnet route added: {wifi_subnet} via wlan0")
            else:
                logger.info(f"ℹ️ WiFi subnet route: {wifi_subnet_result.stderr}")

            # Add Ethernet subnet route with lower metric (primary)
            if eth_subnet:
                eth_subnet_result = subprocess.run([
                    "ip", "route", "add", eth_subnet, "dev", eth_interface, "scope", "link", "metric", "100"
                ], capture_output=True, text=True)

                if eth_subnet_result.returncode == 0:
                    logger.info(f"✅ Ethernet subnet route added: {eth_subnet} via {eth_interface}")
                else:
                    logger.info(f"ℹ️ Ethernet subnet route: {eth_subnet_result.stderr}")

            # CRITICAL: Ensure both interfaces can receive traffic destined for their IPs
            # Add host routes for direct IP access
            subprocess.run([
                "ip", "route", "add", f"{wifi_ip}/32", "dev", "wlan0", "scope", "host"
            ], capture_output=True)

            if eth_ip:
                subprocess.run([
                    "ip", "route", "add", f"{eth_ip}/32", "dev", eth_interface, "scope", "host"
                ], capture_output=True)

            logger.info("✅ CRITICAL FIX: Host routes added for direct IP access")

            # Step 6: Test both interfaces (reference approach)
            logger.info("🧪 REFERENCE: Testing network interface accessibility...")
            logger.info(f"   📶 WiFi should be accessible at: http://{wifi_ip}:8123/")
            if eth_ip:
                logger.info(f"   🔌 Ethernet should be accessible at: http://{eth_ip}:8123/")

            # Step 7: CRITICAL VERIFICATION - Test WiFi IP accessibility after dual setup
            logger.info("🔍 CRITICAL VERIFICATION: Testing WiFi IP accessibility after dual network setup...")

            # Verify WiFi IP is still in interface
            wifi_verify = subprocess.run(["ip", "addr", "show", "wlan0"], capture_output=True, text=True)
            wifi_ip_present = wifi_ip in wifi_verify.stdout

            # Test local ping to WiFi IP
            wifi_ping = subprocess.run([
                "ping", "-c", "1", "-W", "2", wifi_ip
            ], capture_output=True, text=True)
            wifi_ping_ok = wifi_ping.returncode == 0

            logger.info(f"   WiFi IP in interface: {'✅' if wifi_ip_present else '❌'}")
            logger.info(f"   WiFi IP ping test: {'✅' if wifi_ping_ok else '❌'}")

            if not wifi_ip_present or not wifi_ping_ok:
                logger.error(f"❌ CRITICAL: WiFi IP {wifi_ip} not accessible after dual network setup!")
                logger.error("🔧 Attempting to restore WiFi IP accessibility...")

                # Emergency fix: Re-add WiFi IP and routes
                subprocess.run([
                    "ip", "addr", "add", f"{wifi_ip}/24", "dev", "wlan0"
                ], capture_output=True)

                wifi_subnet = '.'.join(wifi_ip.split('.')[:-1]) + '.0/24'
                subprocess.run([
                    "ip", "route", "add", wifi_subnet, "dev", "wlan0", "scope", "link", "metric", "200"
                ], capture_output=True)

                subprocess.run([
                    "ip", "route", "add", f"{wifi_ip}/32", "dev", "wlan0", "scope", "host"
                ], capture_output=True)

                logger.info("🔧 Emergency WiFi IP restoration attempted")
            else:
                logger.info("✅ WiFi IP accessibility verified after dual network setup")

            logger.info(f"✅ REFERENCE DUAL NETWORK CONFIGURED:")
            logger.info(f"   📶 WiFi: http://{wifi_ip}:8123 (metric 200 - backup)")
            if eth_ip:
                logger.info(f"   🔌 Ethernet: http://{eth_ip}:8123 (metric 100 - primary)")
            logger.info(f"   🌐 Both IPs should be accessible for Home Assistant")

        return True

    def connect_to_network(self, ssid: str, password: str) -> Dict[str, str]:
        """Connect to a WiFi network with improved error handling and LED status updates"""
        try:
            logger.info(f"🔗 Attempting to connect to WiFi network: {ssid}")

            # DON'T set LED to connecting state here - only after successful connection
            # set_led_status('wifi_connecting')  # REMOVED - premature LED change
            
            # Save config for persistence
            config = {
                "ssid": ssid,
                "password": password,
                "timestamp": time.time(),
                "static_ip": os.getenv("STATIC_IP", "192.168.6.161"),
                "static_gateway": os.getenv("STATIC_GATEWAY", "192.168.6.1"),
                "static_dns": os.getenv("STATIC_DNS", "8.8.8.8"),
                "use_static_ip": os.getenv("USE_STATIC_IP", "true") == "true"
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Create wpa_supplicant configuration
            logger.info("📝 Creating wpa_supplicant configuration...")
            
            # Try to use wpa_passphrase for proper PSK generation (handles special characters better)
            try:
                logger.info("🔧 Generating PSK using wpa_passphrase...")
                wpa_passphrase_result = subprocess.run([
                    "wpa_passphrase", ssid, password
                ], capture_output=True, text=True, timeout=10)
                
                if wpa_passphrase_result.returncode == 0:
                    # Use the generated configuration but add our custom settings
                    generated_config = wpa_passphrase_result.stdout
                    
                    # Modify the generated config to add our custom settings
                    lines = generated_config.split('\n')
                    modified_lines = []
                    in_network_block = False
                    
                    for line in lines:
                        if 'network={' in line:
                            in_network_block = True
                            modified_lines.append(line)
                            modified_lines.append('    priority=1')
                            modified_lines.append('    scan_ssid=1')
                            modified_lines.append('    auth_alg=OPEN')
                        elif in_network_block and line.strip() == '}':
                            modified_lines.append(line)
                            in_network_block = False
                        elif not (line.strip().startswith('#') and 'psk=' in line):
                            # Skip commented out PSK lines
                            modified_lines.append(line)
                    
                    # Add header
                    wpa_config = f'''ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=US

{chr(10).join(modified_lines)}
'''
                    logger.info("✅ Using wpa_passphrase generated configuration")
                else:
                    raise Exception(f"wpa_passphrase failed: {wpa_passphrase_result.stderr}")
                    
            except Exception as e:
                logger.warning(f"⚠️ wpa_passphrase failed ({e}), using manual configuration")
                # Fallback to manual configuration with proper escaping
                escaped_ssid = ssid.replace('"', '\\"').replace('\\', '\\\\')
                escaped_password = password.replace('"', '\\"').replace('\\', '\\\\')
                
                wpa_config = f'''ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=US

network={{
    ssid="{escaped_ssid}"
    psk="{escaped_password}"
    key_mgmt=WPA-PSK
    priority=1
    scan_ssid=1
    auth_alg=OPEN
}}
'''
            
            with open(self.wpa_conf_path, 'w') as f:
                f.write(wpa_config)
            
            # Debug: log the configuration (without exposing the actual password)
            debug_config = wpa_config.replace(password, "***PASSWORD_HIDDEN***")
            logger.info(f"📝 wpa_supplicant configuration written:\n{debug_config}")
            
            # Ensure wlan0 interface is up
            logger.info("🔌 Bringing up wlan0 interface...")
            subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)
            
            # Kill existing wpa_supplicant processes
            logger.info("🔧 Stopping existing wpa_supplicant...")
            subprocess.run(["pkill", "-f", "wpa_supplicant"], capture_output=True)
            time.sleep(2)
            
            # Start wpa_supplicant with detailed logging
            logger.info("🔧 Starting wpa_supplicant...")
            wpa_result = subprocess.run([
                "wpa_supplicant", "-B", "-i", "wlan0", 
                "-c", self.wpa_conf_path, "-D", "nl80211", "-dd"
            ], capture_output=True, text=True)
            
            if wpa_result.returncode != 0:
                logger.error(f"❌ wpa_supplicant failed: {wpa_result.stderr}")
                logger.error(f"❌ wpa_supplicant stdout: {wpa_result.stdout}")
                
                # Provide more user-friendly error message that Flutter can detect as password-related
                error_msg = wpa_result.stderr.lower()
                if ('psk' in error_msg or 'password' in error_msg or 'auth' in error_msg or 
                    'key' in error_msg or 'invalid' in error_msg or 'fail' in error_msg):
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                else:
                    return {"status": "error", "error": f"wpa_supplicant authentication error: {wpa_result.stderr}"}
            
            # Give wpa_supplicant a moment to initialize
            logger.info("⏱️ Allowing wpa_supplicant to initialize...")
            time.sleep(3)
            
            logger.info("⏱️ Waiting for WiFi authentication...")
            # Wait for connection with better status monitoring (increased timeout)
            for attempt in range(20):  # 20 seconds timeout - better for slower networks
                time.sleep(1)
                status_result = subprocess.run(["wpa_cli", "-i", "wlan0", "status"], capture_output=True, text=True)
                
                if status_result.returncode != 0:
                    logger.warning(f"⚠️ wpa_cli status failed: {status_result.stderr}")
                    continue
                
                status_output = status_result.stdout
                logger.info(f"📊 WPA Status (attempt {attempt+1}): {status_output.split(chr(10))[0]}")
                
                if "wpa_state=COMPLETED" in status_output:
                    logger.info("✅ WiFi authentication successful")
                    break
                elif "wpa_state=DISCONNECTED" in status_output:
                    logger.warning("⚠️ WiFi authentication failed - likely wrong password")
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                elif "wpa_state=SCANNING" in status_output:
                    logger.info("🔍 Still scanning for network...")
                elif "wpa_state=ASSOCIATING" in status_output:
                    logger.info("🔗 Associating with network...")
                elif "wpa_state=4WAY_HANDSHAKE" in status_output:
                    logger.info("🤝 Performing 4-way handshake...")
                elif "wpa_state=INTERFACE_DISABLED" in status_output:
                    logger.warning("⚠️ WiFi interface disabled - possible authentication failure")
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
            else:
                # Get final status for debugging
                final_result = subprocess.run(["wpa_cli", "-i", "wlan0", "status"], capture_output=True, text=True)
                final_status = final_result.stdout
                logger.error(f"❌ Authentication timeout. Final status: {final_status}")
                
                # Provide user-friendly error based on final status
                if "wpa_state=DISCONNECTED" in final_status:
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                elif "wpa_state=SCANNING" in final_status:
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                elif "wpa_state=ASSOCIATING" in final_status:
                    # Association timeout is usually a password issue
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                elif "wpa_state=4WAY_HANDSHAKE" in final_status:
                    # 4-way handshake timeout is definitely a password issue
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                else:
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
            
            # Get IP address and ensure immediate accessibility
            if config["use_static_ip"]:
                logger.info(f"🔧 Configuring static IP for immediate accessibility: {config['static_ip']}")
                
                # Remove existing IP addresses on wlan0 only
                subprocess.run(["ip", "addr", "flush", "dev", "wlan0"], capture_output=True)
                
                # Add static IP with immediate effect
                ip_result = subprocess.run([
                    "ip", "addr", "add", f"{config['static_ip']}/24", "dev", "wlan0"
                ], capture_output=True, text=True)
                
                if ip_result.returncode != 0:
                    logger.error(f"❌ Failed to set static IP: {ip_result.stderr}")
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}
                
                # Ensure interface is up and immediately accessible
                subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)
                
                # Add default route for WiFi static IP
                subprocess.run([
                    "ip", "route", "add", "default", "via", config["static_gateway"], 
                    "dev", "wlan0", "metric", "100"
                ], capture_output=True)
                
                # IMMEDIATE ACTIVATION: Ensure WiFi interface is immediately accessible
                wifi_ip = config["static_ip"]
                logger.info(f"🚀 IMMEDIATE ACTIVATION: Making WiFi {wifi_ip} accessible for Home Assistant...")

                # Force interface up and verify IP is active
                subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)

                # CRITICAL: Verify IP is assigned and active before routing
                ip_verify = subprocess.run(["ip", "addr", "show", "wlan0"], capture_output=True, text=True)
                if wifi_ip in ip_verify.stdout:
                    logger.info(f"✅ WiFi IP {wifi_ip} is active and ready")
                else:
                    logger.warning(f"⚠️ WiFi IP {wifi_ip} not found in interface, forcing assignment...")
                    # Force IP assignment if not present
                    subprocess.run([
                        "ip", "addr", "add", f"{wifi_ip}/24", "dev", "wlan0"
                    ], capture_output=True)

                    # Verify assignment worked
                    ip_verify2 = subprocess.run(["ip", "addr", "show", "wlan0"], capture_output=True, text=True)
                    if wifi_ip in ip_verify2.stdout:
                        logger.info(f"✅ WiFi IP {wifi_ip} successfully assigned")
                    else:
                        logger.error(f"❌ Failed to assign WiFi IP {wifi_ip}")
                        return {"status": "error", "error": "Failed to configure WiFi IP address"}

                # Setup dual network routing for immediate access
                has_ethernet = self._setup_dual_network_routing(
                    wifi_ip=wifi_ip,
                    wifi_gateway=config["static_gateway"],
                    is_static=True
                )

                ip_address = wifi_ip

                # FINAL VERIFICATION: Ensure WiFi IP is accessible for Home Assistant
                final_check = subprocess.run(["ip", "addr", "show", "wlan0"], capture_output=True, text=True)
                route_check = subprocess.run(["ip", "route", "show", "dev", "wlan0"], capture_output=True, text=True)

                logger.info(f"🔍 Final WiFi verification:")
                logger.info(f"   IP assigned: {'✅' if wifi_ip in final_check.stdout else '❌'}")
                logger.info(f"   Routes configured: {'✅' if wifi_ip in route_check.stdout else '❌'}")

                # Test local connectivity to the WiFi IP
                ping_test = subprocess.run([
                    "ping", "-c", "1", "-W", "2", wifi_ip
                ], capture_output=True, text=True)

                logger.info(f"   Local ping test: {'✅' if ping_test.returncode == 0 else '❌'}")

                if wifi_ip in final_check.stdout and ping_test.returncode == 0:
                    logger.info(f"🎯 WiFi Home Assistant IMMEDIATELY accessible at: http://{ip_address}:8123")
                else:
                    logger.error(f"❌ WiFi IP {wifi_ip} verification failed - not accessible")
                    logger.error(f"   IP check: {'✅' if wifi_ip in final_check.stdout else '❌'}")
                    logger.error(f"   Ping test: {'✅' if ping_test.returncode == 0 else '❌'}")
                    # Don't return error - continue with connection but log the issue
                    logger.warning("⚠️ Continuing despite verification issues...")

                # Immediate LED update for successful connection
                update_network_led_status()
            else:
                logger.info("🔧 Using DHCP for IP configuration")
                dhcp_result = subprocess.run(["dhclient", "wlan0"], capture_output=True, text=True)
                
                if dhcp_result.returncode != 0:
                    logger.warning(f"⚠️ DHCP client warning: {dhcp_result.stderr}")
                
                # IMMEDIATE ACTIVATION: Reduce wait time and ensure interface is ready
                time.sleep(2)  # Reduced from 5 to 2 seconds for faster access

                # Force interface up for immediate access
                subprocess.run(["ip", "link", "set", "wlan0", "up"], capture_output=True)

                # Get assigned IP with multiple attempts for reliability
                ip_address = "unknown"
                for attempt in range(3):  # Try 3 times for reliability
                    ip_result = subprocess.run(["ip", "addr", "show", "wlan0"], capture_output=True, text=True)
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout)
                    if ip_match:
                        ip_address = ip_match.group(1)
                        break
                    time.sleep(1)  # Wait 1 second between attempts

                if ip_address == "unknown":
                    logger.error("❌ No IP address assigned after multiple attempts")
                    return {"status": "auth_failed", "error": "Please re-enter correct password"}

                logger.info(f"🚀 DHCP WiFi IP {ip_address} assigned and ready for immediate access")
                
                # Get the WiFi gateway for DHCP configuration
                route_check = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
                wifi_gateway = None

                # Find WiFi gateway from routing table
                for route_line in route_check.stdout.split('\n'):
                    if 'wlan0' in route_line and 'default' in route_line:
                        parts = route_line.split()
                        if 'via' in parts:
                            gateway_idx = parts.index('via') + 1
                            if gateway_idx < len(parts):
                                wifi_gateway = parts[gateway_idx]
                                break

                # If no gateway found, try to get it from the interface
                if not wifi_gateway:
                    # Get gateway from DHCP lease or interface configuration
                    gateway_result = subprocess.run(["ip", "route", "show", "dev", "wlan0"], capture_output=True, text=True)
                    for line in gateway_result.stdout.split('\n'):
                        if 'default' in line and 'via' in line:
                            parts = line.split()
                            if 'via' in parts:
                                gateway_idx = parts.index('via') + 1
                                if gateway_idx < len(parts):
                                    wifi_gateway = parts[gateway_idx]
                                    break

                # Setup dual network routing using the helper function
                if wifi_gateway:
                    has_ethernet = self._setup_dual_network_routing(
                        wifi_ip=ip_address,
                        wifi_gateway=wifi_gateway,
                        is_static=False
                    )
                    logger.info(f"🎯 DHCP WiFi Home Assistant IMMEDIATELY accessible at: http://{ip_address}:8123")
                else:
                    logger.warning("⚠️ Could not determine WiFi gateway for DHCP configuration")
                    # Fallback: just check if Ethernet exists
                    eth_status = self._check_ethernet_connection()
                    has_ethernet = eth_status['connected']
                    logger.info(f"🎯 WiFi IP {ip_address} configured (no gateway found)")

                # Force immediate LED update
                update_network_led_status()
            
            logger.info(f"📡 Assigned IP address: {ip_address}")
            
            # Check network access status for proper reporting
            eth_status = self._check_ethernet_connection()
            has_ethernet = eth_status['connected']
            eth_ip = eth_status['ip']
            
            # Verify connectivity
            logger.info("🔍 Testing internet connectivity...")
            ping_result = subprocess.run(["ping", "-c", "3", "-W", "5", "8.8.8.8"], capture_output=True, text=True)
            
            # Prepare connection status with dual network info
            connection_result = {
                "status": "connected",
                "ip": ip_address,
                "wifi_ip": ip_address,
                "ssid": ssid,
                "hub_url": f"http://{ip_address}:8123"
            }
            
            # Get MAC address and save IP to Firestore
            mac_address = get_mac_address()
            if mac_address:
                connection_result["mac_address"] = mac_address
                logger.info(f"📍 Hub MAC Address: {mac_address}")
                
                # Save IP to Firestore
                if FIRESTORE_AVAILABLE:
                    try:
                        firestore_helper = FirestoreHelper()
                        success = firestore_helper.save_hub_ip(mac_address, ip_address)
                        if success:
                            logger.info(f"✅ IP saved to Firestore: smash_db/{mac_address}/home_ip = {ip_address}")
                        else:
                            logger.warning(f"⚠️ Failed to save IP to Firestore")
                    except Exception as e:
                        logger.error(f"❌ Error saving IP to Firestore: {e}")
                else:
                    logger.warning("⚠️ Firestore not available, IP not saved to database")
            else:
                logger.warning("⚠️ Could not get MAC address, IP not saved to Firestore")
            
            # Add Ethernet information if available
            if has_ethernet and eth_ip:
                connection_result.update({
                    "ethernet_ip": eth_ip,
                    "connection_type": "dual_network",
                    "ethernet_hub_url": f"http://{eth_ip}:8123",
                    "message": f"WiFi connected at {ip_address}. Ethernet remains accessible at {eth_ip}"
                })
                logger.info(f"🌐 Dual network access: WiFi={ip_address}, Ethernet={eth_ip}")
            else:
                connection_result.update({
                    "connection_type": "wifi_only",
                    "message": f"WiFi connected at {ip_address}"
                })
                logger.info(f"📶 WiFi-only access: {ip_address}")
            
            if ping_result.returncode == 0:
                logger.info(f"✅ WiFi connection successful with internet access!")
                # Use comprehensive LED status check
                update_network_led_status()
                return connection_result
            else:
                logger.warning(f"⚠️ WiFi connected but no internet access via WiFi: {ping_result.stderr}")
                connection_result["status"] = "connected_no_internet"
                # Use comprehensive LED status check
                update_network_led_status()
                return connection_result
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to WiFi: {e}")
            set_led_status('error')
            return {"status": "auth_failed", "error": "Please re-enter correct password"}

    def load_saved_config(self) -> Optional[Dict]:
        """Load saved Wi-Fi configuration."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

                ssid = config.get('ssid', '').strip()
                if ssid:
                    logger.info(f"Loaded Wi-Fi config for network: {ssid}")
                    return config
                else:
                    logger.warning("Config file exists but no SSID found")

        except Exception as e:
            logger.error(f"Error loading Wi-Fi config: {e}")

        return None

    def save_config(self, ssid: str, password: str) -> bool:
        """Save Wi-Fi configuration."""
        try:
            config = {
                'ssid': ssid,
                'password': password,
                'configured': True,
                'use_static_ip': os.getenv('USE_STATIC_IP', 'true').lower() == 'true',
                'static_ip': os.getenv('STATIC_IP', '192.168.6.161'),
                'static_gateway': os.getenv('STATIC_GATEWAY', '192.168.6.1'),
                'static_dns': os.getenv('STATIC_DNS', '8.8.8.8'),
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')
            }

            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Wi-Fi configuration saved for network: {ssid}")
            return True

        except Exception as e:
            logger.error(f"Error saving Wi-Fi config: {e}")
            return False

    def clear_config(self) -> bool:
        """Clear saved Wi-Fi configuration (factory reset)."""
        try:
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
                logger.info("Wi-Fi configuration cleared (factory reset)")

            # Also clear any reset flags
            reset_flag = "/tmp/wifi_reset"
            if os.path.exists(reset_flag):
                os.remove(reset_flag)

            return True

        except Exception as e:
            logger.error(f"Error clearing Wi-Fi config: {e}")
            return False

class BLEGATTService:
    """Enhanced GATT service implementation with network list pagination"""
    
    WIFI_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
    WIFI_NETWORKS_CHAR_UUID = "12345678-1234-1234-1234-123456789abd"
    WIFI_CREDENTIALS_CHAR_UUID = "12345678-1234-1234-1234-123456789abe"
    WIFI_STATUS_CHAR_UUID = "12345678-1234-1234-1234-123456789abf"
    DEVICE_INFO_CHAR_UUID = "12345678-1234-1234-1234-123456789ac0"
    NETWORK_PAGE_CHAR_UUID = "12345678-1234-1234-1234-123456789ac1"  # For pagination
    
    def __init__(self, wifi_controller):
        self.wifi_controller = wifi_controller
        self.device_name = self._get_device_name()
        self.bus = None
        self.service_manager = None
        self.advertisement_manager = None
        self.current_status = {"status": "ready", "message": "Ready for WiFi configuration"}
        self.is_advertising = False
        self.advertising_stopped_after_wifi = False
        
    def _get_device_name(self) -> str:
        """Get device name from MAC address"""
        try:
            result = subprocess.run(['cat', '/sys/class/net/wlan0/address'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                mac_address = result.stdout.strip().replace(':', '').upper()[-4:]
                return f"SMASH-{mac_address}"
            return "SMASH-1234"
        except Exception as e:
            logger.warning(f"Could not get MAC address: {e}")
            return "SMASH-1234"

    def stop_advertising(self):
        """Stop BLE advertising after WiFi connection"""
        try:
            if self.advertisement_manager and self.is_advertising:
                logger.info("📴 STOPPING BLE ADVERTISING: WiFi connected - no longer discoverable")

                # Find adapter path
                adapter_path = None
                for adapter_name in ['hci0', 'hci1']:
                    try:
                        adapter_path = f'/org/bluez/{adapter_name}'
                        adapter_obj = self.bus.get_object('org.bluez', adapter_path)
                        break
                    except:
                        continue

                if adapter_path:
                    adv_manager = dbus.Interface(
                        self.bus.get_object('org.bluez', adapter_path),
                        'org.bluez.LEAdvertisingManager1'
                    )

                    # Unregister advertisement
                    adv_manager.UnregisterAdvertisement(self.advertisement_manager.get_path())
                    logger.info("✅ BLE advertising stopped - device no longer discoverable")
                    self.is_advertising = False
                    self.advertising_stopped_after_wifi = True
                else:
                    logger.warning("⚠️  Could not find Bluetooth adapter to stop advertising")

        except Exception as e:
            logger.warning(f"⚠️  Failed to stop BLE advertising: {e}")

    def start_advertising(self):
        """Start BLE advertising for WiFi onboarding"""
        try:
            if not self.is_advertising:
                logger.info("📡 STARTING BLE ADVERTISING: Device discoverable for WiFi onboarding")

                # Find adapter path
                adapter_path = None
                for adapter_name in ['hci0', 'hci1']:
                    try:
                        adapter_path = f'/org/bluez/{adapter_name}'
                        adapter_obj = self.bus.get_object('org.bluez', adapter_path)
                        break
                    except:
                        continue

                if adapter_path and self.advertisement_manager:
                    adv_manager = dbus.Interface(
                        self.bus.get_object('org.bluez', adapter_path),
                        'org.bluez.LEAdvertisingManager1'
                    )

                    # Register advertisement
                    adv_manager.RegisterAdvertisement(
                        self.advertisement_manager.get_path(),
                        {},
                        reply_handler=lambda: self._advertising_registered(),
                        error_handler=lambda error: logger.error(f"❌ Advertisement registration failed: {error}")
                    )
                else:
                    logger.warning("⚠️  Could not find Bluetooth adapter or advertisement manager not initialized")

        except Exception as e:
            logger.warning(f"⚠️  Failed to start BLE advertising: {e}")

    def _advertising_registered(self):
        """Callback when advertising is successfully registered"""
        logger.info("✅ BLE advertising started - device discoverable as 'SMASH-Hub'")
        self.is_advertising = True
        self.advertising_stopped_after_wifi = False

    def restart_advertising_after_factory_reset(self):
        """Restart BLE advertising after factory reset"""
        logger.info("🔄 FACTORY RESET: Restarting BLE advertising for fresh WiFi onboarding")
        self.advertising_stopped_after_wifi = False
        self.start_advertising()

    def start_service(self) -> bool:
        """Start the BLE GATT service"""
        if not DBUS_AVAILABLE:
            logger.error("❌ D-Bus libraries not available. Cannot start BLE service.")
            return False
        
        try:
            # Initialize D-Bus
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.bus = dbus.SystemBus()
            
            # Check if BlueZ is available
            try:
                bluez_obj = self.bus.get_object('org.bluez', '/')
                logger.info("✅ BlueZ D-Bus service is available")
            except dbus.exceptions.DBusException as e:
                logger.error(f"❌ BlueZ not available: {e}")
                return False
            
            # Find and configure adapter
            adapter_path = self._find_adapter()
            if not adapter_path:
                logger.error("❌ No Bluetooth adapter found")
                return False
            
            logger.info(f"📡 Using Bluetooth adapter: {adapter_path}")
            
            # Power on and configure adapter
            adapter_props = dbus.Interface(
                self.bus.get_object('org.bluez', adapter_path),
                'org.freedesktop.DBus.Properties'
            )
            adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(1))
            adapter_props.Set('org.bluez.Adapter1', 'Alias', dbus.String(self.device_name))
            adapter_props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(1))
            adapter_props.Set('org.bluez.Adapter1', 'DiscoverableTimeout', dbus.UInt32(0))
            
            logger.info(f"🔌 Configured adapter as '{self.device_name}'")
            
            # Create and register GATT service
            self.service_manager = SmashGATTApplication(self.bus, self.wifi_controller)
            gatt_manager = dbus.Interface(
                self.bus.get_object('org.bluez', adapter_path),
                'org.bluez.GattManager1'
            )
            
            logger.info("📋 Registering GATT service...")
            gatt_manager.RegisterApplication(
                self.service_manager.get_path(),
                {},
                reply_handler=lambda: logger.info("✅ GATT service registered"),
                error_handler=lambda error: logger.error(f"❌ GATT service registration failed: {error}")
            )
            
            # Create and register advertisement
            self.advertisement_manager = SmashAdvertisement(
                self.bus, 0, self.device_name, self.WIFI_SERVICE_UUID
            )
            adv_manager = dbus.Interface(
                self.bus.get_object('org.bluez', adapter_path),
                'org.bluez.LEAdvertisingManager1'
            )
            
            logger.info("📢 Registering advertisement...")
            adv_manager.RegisterAdvertisement(
                self.advertisement_manager.get_path(),
                {},
                reply_handler=lambda: self._advertising_registered(),
                error_handler=lambda error: logger.error(f"❌ Advertisement registration failed: {error}")
            )
            
            # Start the GLib main loop
            logger.info("🔄 Starting BLE service main loop...")
            logger.info(f"📱 Device '{self.device_name}' is now discoverable!")
            logger.info(f"🔧 Service UUID: {self.WIFI_SERVICE_UUID}")
            
            mainloop = GLib.MainLoop()
            mainloop.run()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start BLE service: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return False
    
    def _find_adapter(self) -> Optional[str]:
        """Find the first available Bluetooth adapter"""
        try:
            manager = dbus.Interface(
                self.bus.get_object('org.bluez', '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            objects = manager.GetManagedObjects()
            
            for path, interfaces in objects.items():
                if 'org.bluez.Adapter1' in interfaces:
                    return str(path)
            
            return None
        except Exception as e:
            logger.error(f"Error finding adapter: {e}")
            return None

# GATT Application and Service classes
if DBUS_AVAILABLE:
    class SmashGATTApplication(dbus.service.Object):
        """Main GATT Application"""
        
        def __init__(self, bus, wifi_controller):
            self.path = '/org/bluez/smash/application'
            self.bus = bus
            self.wifi_controller = wifi_controller
            
            dbus.service.Object.__init__(self, bus, self.path)
            
            # Create the main service
            self.service = SmashWiFiService(bus, 0, wifi_controller)
            
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        @dbus.service.method('org.freedesktop.DBus.ObjectManager',
                             out_signature='a{oa{sa{sv}}}')
        def GetManagedObjects(self):
            response = {}
            response[self.service.get_path()] = self.service.get_properties()
            
            # Add characteristics
            for char in self.service.characteristics:
                response[char.get_path()] = char.get_properties()
            
            return response
    
    class SmashWiFiService(dbus.service.Object):
        """Main WiFi Configuration Service"""
        
        def __init__(self, bus, index, wifi_controller):
            self.path = f'/org/bluez/smash/service{index}'
            self.bus = bus
            self.wifi_controller = wifi_controller
            self.uuid = BLEGATTService.WIFI_SERVICE_UUID
            self.primary = True
            
            dbus.service.Object.__init__(self, bus, self.path)
            
            # Create characteristics
            self.characteristics = []
            self.characteristics.append(WiFiNetworksCharacteristic(bus, 0, self))
            self.characteristics.append(WiFiCredentialsCharacteristic(bus, 1, self))
            self.status_characteristic = WiFiStatusCharacteristic(bus, 2, self)
            self.characteristics.append(self.status_characteristic)
            self.characteristics.append(DeviceInfoCharacteristic(bus, 3, self))
            self.characteristics.append(NetworkPageCharacteristic(bus, 4, self))
            
            # Network pagination state
            self.cached_networks = []
            self.networks_per_page = 3  # Reduce to 3 to ensure BLE characteristic fit
            self.cache_expiry = 30  # Cache networks for 30 seconds
            self.last_scan_time = 0
            
            # Initialize current status
            self.current_status = {"status": "ready", "message": "Ready for WiFi configuration"}
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattService1': {
                    'UUID': self.uuid,
                    'Primary': self.primary,
                    'Characteristics': dbus.Array([char.get_path() for char in self.characteristics], 'o')
                }
            }
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattService1':
                raise dbus.exceptions.DBusException('Invalid interface', name='org.freedesktop.DBus.Error.InvalidArgs')
            return self.get_properties()['org.bluez.GattService1']
        
        def get_networks_page(self, page: int = 0) -> Dict:
            """Get a page of WiFi networks with caching"""
            current_time = time.time()
            
            # Refresh cache if expired or empty
            if not self.cached_networks or (current_time - self.last_scan_time) > self.cache_expiry:
                logger.info("🔄 Refreshing WiFi network cache...")
                self.cached_networks = self.wifi_controller.get_available_networks()
                self.last_scan_time = current_time
                logger.info(f"📡 Cached {len(self.cached_networks)} networks")
            
            # Calculate pagination
            total_networks = len(self.cached_networks)
            total_pages = (total_networks + self.networks_per_page - 1) // self.networks_per_page
            start_idx = page * self.networks_per_page
            end_idx = min(start_idx + self.networks_per_page, total_networks)
            
            # Get networks for this page
            page_networks = []
            for net in self.cached_networks[start_idx:end_idx]:
                page_networks.append({
                    'ssid': net['ssid'],
                    'signal_strength': net.get('signal_strength', -50),
                    'bssid': net.get('bssid', ''),
                    'security': 'WPA2'  # Simplified for now
                })
            
            return {
                'networks': page_networks,
                'page': page,
                'per_page': self.networks_per_page,
                'total_pages': total_pages,
                'total_networks': total_networks,
                'has_next': page < (total_pages - 1),
                'has_prev': page > 0
            }
        
        def notify_status_change(self, status_data):
            """Notify clients of status changes via BLE notifications"""
            try:
                logger.info(f"🔔 Notifying status change: {status_data.get('status', 'unknown')}")
                
                # Update current status
                self.current_status = status_data
                
                # Notify via the status characteristic if it supports notifications
                if hasattr(self, 'status_characteristic') and self.status_characteristic.notifying:
                    # Create notification data
                    response = json.dumps(status_data, separators=(',', ':'))
                    
                    # Send D-Bus PropertiesChanged signal
                    self.status_characteristic.PropertiesChanged(
                        'org.bluez.GattCharacteristic1',
                        {'Value': dbus.Array([dbus.Byte(c) for c in response.encode('utf-8')], signature='y')},
                        []
                    )
                    logger.info(f"📡 Status notification sent to BLE clients")
                else:
                    logger.info("📡 No clients subscribed to notifications")
                    
            except Exception as e:
                logger.error(f"❌ Failed to send status notification: {e}")
    
    class WiFiNetworksCharacteristic(dbus.service.Object):
        """Characteristic for reading available WiFi networks"""
        
        def __init__(self, bus, index, service):
            self.path = f'{service.path}/char{index}'
            self.bus = bus
            self.service = service
            self.uuid = BLEGATTService.WIFI_NETWORKS_CHAR_UUID
            self.flags = ['read']
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattCharacteristic1': {
                    'UUID': self.uuid,
                    'Service': self.service.get_path(),
                    'Flags': self.flags
                }
            }
        
        @dbus.service.method('org.bluez.GattCharacteristic1', out_signature='ay')
        def ReadValue(self, options):
            logger.info("📡 Client requested WiFi networks (page 0)")
            
            # Get first page of networks
            page_data = self.service.get_networks_page(0)
            
            # Create compact JSON response
            response = json.dumps(page_data, separators=(',', ':'))
            logger.info(f"📤 Sending page 0: {len(page_data['networks'])} networks (JSON size: {len(response)} bytes)")
            
            # Ensure response fits in BLE characteristic (max ~512 bytes)
            if len(response) > 400:  # Leave some margin
                # Fall back to limited response
                limited_data = {
                    'networks': page_data['networks'][:3],
                    'page': 0,
                    'per_page': 3,
                    'total_pages': page_data['total_pages'],
                    'total_networks': page_data['total_networks'],
                    'has_next': page_data['total_networks'] > 3,
                    'has_prev': False
                }
                response = json.dumps(limited_data, separators=(',', ':'))
                logger.warning(f"📦 Response too large, limited to 3 networks ({len(response)} bytes)")
            
            return [dbus.Byte(c) for c in response.encode('utf-8')]
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattCharacteristic1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.GattCharacteristic1']
    
    class WiFiCredentialsCharacteristic(dbus.service.Object):
        """Characteristic for writing WiFi credentials"""
        
        def __init__(self, bus, index, service):
            self.path = f'{service.path}/char{index}'
            self.bus = bus
            self.service = service
            self.uuid = BLEGATTService.WIFI_CREDENTIALS_CHAR_UUID
            self.flags = ['write']
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattCharacteristic1': {
                    'UUID': self.uuid,
                    'Service': self.service.get_path(),
                    'Flags': self.flags
                }
            }
        
        @dbus.service.method('org.bluez.GattCharacteristic1', in_signature='aya{sv}')
        def WriteValue(self, value, options):
            try:
                data = bytes([v for v in value]).decode('utf-8')
                credentials = json.loads(data)
                
                ssid = credentials.get('ssid')
                password = credentials.get('password')
                
                logger.info(f"🔑 Received WiFi credentials for: {ssid}")
                
                # Set connecting status
                connecting_status = {
                    'status': 'connecting',
                    'message': 'Connecting to WiFi...', 
                    'ssid': ssid
                }
                self.service.current_status = connecting_status
                # Immediately notify clients we're connecting
                self.service.notify_status_change(connecting_status)
                
                # Start connection in background thread to avoid blocking BLE
                connection_thread = threading.Thread(
                    target=self._connect_wifi_async, 
                    args=(ssid, password)
                )
                connection_thread.daemon = True
                connection_thread.start()
                
            except Exception as e:
                logger.error(f"❌ Error processing credentials: {e}")
                self.service.current_status = {
                    'status': 'error',
                    'error': f'Invalid credentials format: {str(e)}'
                }
        
        def _connect_wifi_async(self, ssid, password):
            """Async WiFi connection with status updates"""
            try:
                # Update status during connection
                connecting_status = {
                    'status': 'connecting',
                    'message': 'Connecting to WiFi...', 
                    'ssid': ssid
                }
                self.service.current_status = connecting_status
                # Notify clients we're connecting
                self.service.notify_status_change(connecting_status)
                
                result = self.service.wifi_controller.connect_to_network(ssid, password)
                logger.info(f"📶 WiFi connection result: {result['status']}")
                
                # Update final status
                if result['status'] == 'connected':
                    logger.info(f"✅ WiFi connected successfully! IP: {result.get('ip', 'unknown')}")
                    status_update = {
                        'status': 'connected',
                        'ssid': ssid,
                        'ip': result.get('ip'),
                        'hub_url': result.get('hub_url'),
                        'message': f'Successfully connected to {ssid}'
                    }
                    self.service.current_status = status_update
                    # Immediately notify clients of status change
                    self.service.notify_status_change(status_update)

                    # CRITICAL: Stop BLE advertising after successful WiFi connection
                    logger.info("🔄 WiFi connected - stopping BLE advertising")
                    self.service.stop_advertising()
                elif result['status'] == 'connected_no_internet':
                    logger.info(f"✅ WiFi connected with static IP: {result.get('ip', 'unknown')}")
                    status_update = {
                        'status': 'connected',  # Report as connected since static IP works
                        'ssid': ssid,
                        'ip': result.get('ip'),
                        'hub_url': result.get('hub_url'),
                        'message': f'Successfully connected to {ssid}'
                    }
                    self.service.current_status = status_update
                    # Immediately notify clients of status change
                    self.service.notify_status_change(status_update)

                    # CRITICAL: Stop BLE advertising after successful WiFi connection (static IP)
                    logger.info("🔄 WiFi connected (static IP) - stopping BLE advertising")
                    self.service.stop_advertising()
                else:
                    logger.error(f"❌ WiFi connection failed: {result.get('error', 'Unknown error')}")
                    # Preserve the specific error type instead of converting everything to 'error'
                    error_status = {
                        'status': result['status'],  # Keep original status (auth_failed, connection_timeout, etc.)
                        'error': result.get('error', 'Connection failed'),
                        'message': result.get('error', 'Connection failed'),
                        'ssid': ssid
                    }
                    self.service.current_status = error_status
                    # Immediately notify clients of error
                    self.service.notify_status_change(error_status)
                
            except Exception as e:
                logger.error(f"❌ Async connection error: {e}")
                error_status = {
                    'status': 'error',
                    'error': str(e),
                    'ssid': ssid
                }
                self.service.current_status = error_status
                # Immediately notify clients of error
                self.service.notify_status_change(error_status)
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattCharacteristic1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.GattCharacteristic1']
    
    class WiFiStatusCharacteristic(dbus.service.Object):
        """Characteristic for reading WiFi connection status"""
        
        def __init__(self, bus, index, service):
            self.path = f'{service.path}/char{index}'
            self.bus = bus
            self.service = service
            self.uuid = BLEGATTService.WIFI_STATUS_CHAR_UUID
            self.flags = ['read', 'notify']
            self.notifying = False
            self.subscribers = []
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattCharacteristic1': {
                    'UUID': self.uuid,
                    'Service': self.service.get_path(),
                    'Flags': self.flags
                }
            }
        
        @dbus.service.method('org.bluez.GattCharacteristic1', out_signature='ay')
        def ReadValue(self, options):
            logger.info("📊 Client requested WiFi status")
            
            # Check current WiFi and ethernet status for comprehensive feedback
            try:
                status = self._get_comprehensive_network_status()
                response = json.dumps(status, separators=(',', ':'))
                return [dbus.Byte(c) for c in response.encode('utf-8')]
                
            except Exception as e:
                logger.error(f"❌ Error getting status: {e}")
                error_status = {
                    'status': 'error',
                    'message': 'Unable to check network status',
                    'user_action': 'Please try connecting again',
                    'error': str(e)
                }
                response = json.dumps(error_status, separators=(',', ':'))
                return [dbus.Byte(c) for c in response.encode('utf-8')]
        
        def _get_comprehensive_network_status(self):
            """Get comprehensive network status including WiFi and Ethernet"""
            
            # Check WiFi status
            wifi_status = self._get_wifi_status()
            
            # Check Ethernet status
            eth_status = self._get_ethernet_status()
            
            # Determine primary connection and user message
            if wifi_status['connected'] and eth_status['connected']:
                # Both connected - provide dual access information
                return {
                    'status': 'connected',
                    'connection_type': 'dual_network',
                    'message': f"✅ Connected via both WiFi and Ethernet",
                    'user_action': 'Your hub is accessible on both networks',
                    'wifi_ip': wifi_status['ip'],
                    'ethernet_ip': eth_status['ip'],
                    'wifi_ssid': wifi_status.get('ssid', 'Unknown'),
                    'primary_url': f"http://{wifi_status['ip']}:8123",
                    'ethernet_url': f"http://{eth_status['ip']}:8123"
                }
            elif wifi_status['connected']:
                # Only WiFi connected
                return {
                    'status': 'connected',
                    'connection_type': 'wifi_only',
                    'message': f"✅ Connected to WiFi: {wifi_status.get('ssid', 'Unknown')}",
                    'user_action': 'Your hub is ready to use',
                    'wifi_ip': wifi_status['ip'],
                    'wifi_ssid': wifi_status.get('ssid', 'Unknown'),
                    'hub_url': f"http://{wifi_status['ip']}:8123"
                }
            elif eth_status['connected']:
                # Only Ethernet connected
                return {
                    'status': 'ethernet_only',
                    'connection_type': 'ethernet_only',
                    'message': f"🌐 Connected via Ethernet only",
                    'user_action': 'WiFi setup available for wireless access',
                    'ethernet_ip': eth_status['ip'],
                    'hub_url': f"http://{eth_status['ip']}:8123"
                }
            else:
                # No connections
                if self.service.current_status.get('status') == 'connecting':
                    return {
                        'status': 'connecting',
                        'message': f"🔗 Connecting to WiFi...",
                        'user_action': 'Please wait while we connect to your network.',
                        'progress': self.service.current_status.get('progress', 'Initializing...')
                    }
                elif self.service.current_status.get('status') == 'error':
                    error_msg = self.service.current_status.get('error', 'Unknown error')
                    
                    # Provide user-friendly error messages
                    if 'auth_failed' in error_msg or 'wrong password' in error_msg.lower() or 'authentication' in error_msg.lower():
                        return {
                            'status': 'auth_failed',
                            'message': f"❌ Incorrect WiFi password.",
                            'user_action': 'Please double-check your password and try again.',
                            'error_details': error_msg,
                            'retry': True
                        }
                    elif 'network_not_found' in error_msg or 'not found' in error_msg.lower():
                        return {
                            'status': 'network_not_found',
                            'message': f"❌ WiFi network not found.",
                            'user_action': 'Please check the network name or try refreshing the list.',
                            'error_details': error_msg,
                            'retry': True
                        }
                    elif 'connection_timeout' in error_msg or 'timeout' in error_msg.lower():
                        return {
                            'status': 'connection_timeout',
                            'message': f"❌ Connection timed out.",
                            'user_action': 'Please check signal strength and try again.',
                            'error_details': error_msg,
                            'retry': True
                        }
                    elif 'DHCP' in error_msg or 'IP' in error_msg:
                        return {
                            'status': 'network_error',
                            'message': f"❌ Network configuration failed.",
                            'user_action': 'Check your router settings and try again.',
                            'error_details': error_msg,
                            'retry': True
                        }
                    else:
                        return {
                            'status': 'connection_error',
                            'message': f"❌ Connection failed.",
                            'user_action': 'Please try selecting a different network or retry.',
                            'error_details': error_msg,
                            'retry': True
                        }
                else:
                    return {
                        'status': 'ready',
                        'message': f"📱 Ready for WiFi setup.",
                        'user_action': 'Select a WiFi network to connect.',
                    }
        
        def _get_wifi_status(self):
            """Get detailed WiFi status"""
            try:
                result = subprocess.run(['wpa_cli', '-i', 'wlan0', 'status'], capture_output=True, text=True)
                if 'wpa_state=COMPLETED' in result.stdout:
                    # Get IP address
                    ip_result = subprocess.run(['ip', 'addr', 'show', 'wlan0'], capture_output=True, text=True)
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout)
                    ip_address = ip_match.group(1) if ip_match else None
                    
                    # Get SSID
                    ssid_match = re.search(r'ssid=(.+)', result.stdout)
                    ssid = ssid_match.group(1) if ssid_match else None
                    
                    # Test internet connectivity
                    ping_result = subprocess.run(['ping', '-c', '1', '-W', '3', '8.8.8.8'], capture_output=True)
                    internet_access = ping_result.returncode == 0
                    
                    return {
                        'connected': True,
                        'ip': ip_address,
                        'ssid': ssid,
                        'internet_access': internet_access
                    }
                else:
                    return {'connected': False}
            except Exception:
                return {'connected': False}
        
        def _get_ethernet_status(self):
            """Get Ethernet status using the centralized helper"""
            # Use the WiFiController's ethernet check method
            eth_status = self.service.wifi_controller._check_ethernet_connection()
            return {
                'connected': eth_status['connected'],
                'ip': eth_status['ip']
            }
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattCharacteristic1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.GattCharacteristic1']
        
        @dbus.service.method('org.bluez.GattCharacteristic1')
        def StartNotify(self):
            logger.info("🔔 Client subscribed to status notifications")
            self.notifying = True
            
        @dbus.service.method('org.bluez.GattCharacteristic1')
        def StopNotify(self):
            logger.info("🔕 Client unsubscribed from status notifications")
            self.notifying = False
        
        @dbus.service.signal('org.freedesktop.DBus.Properties', signature='sa{sv}as')
        def PropertiesChanged(self, interface, changed, invalidated):
            pass
    
    class DeviceInfoCharacteristic(dbus.service.Object):
        """Characteristic for reading device information"""
        
        def __init__(self, bus, index, service):
            self.path = f'{service.path}/char{index}'
            self.bus = bus
            self.service = service
            self.uuid = BLEGATTService.DEVICE_INFO_CHAR_UUID
            self.flags = ['read']
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattCharacteristic1': {
                    'UUID': self.uuid,
                    'Service': self.service.get_path(),
                    'Flags': self.flags
                }
            }
        
        @dbus.service.method('org.bluez.GattCharacteristic1', out_signature='ay')
        def ReadValue(self, options):
            logger.info("ℹ️ Client requested device info")
            
            # Get MAC address
            mac_address = get_mac_address()
            
            info = {
                'device_name': self.service.wifi_controller.device_name if hasattr(self.service.wifi_controller, 'device_name') else 'SMASH-Hub',
                'firmware_version': '1.0.0',
                'hardware_version': 'RPi5',
                'manufacturer': 'Schnell',
                'mac_address': mac_address if mac_address else 'UNKNOWN'
            }
            
            logger.info(f"📍 Sending device info with MAC: {mac_address}")
            
            response = json.dumps(info)
            return [dbus.Byte(c) for c in response.encode('utf-8')]
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattCharacteristic1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.GattCharacteristic1']
    
    class SmashAdvertisement(dbus.service.Object):
        """BLE Advertisement"""
        
        def __init__(self, bus, index, local_name, service_uuid):
            self.path = f'/org/bluez/smash/advertisement{index}'
            self.bus = bus
            self.ad_type = 'peripheral'
            self.service_uuids = [service_uuid]
            self.local_name = local_name
            self.include_tx_power = True
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.LEAdvertisement1': {
                    'Type': self.ad_type,
                    'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                    'LocalName': dbus.String(self.local_name),
                    'IncludeTxPower': dbus.Boolean(self.include_tx_power),
                }
            }
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.LEAdvertisement1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.LEAdvertisement1']
        
        @dbus.service.method('org.bluez.LEAdvertisement1')
        def Release(self):
            logger.info(f'📢 Advertisement released: {self.path}')
    
    class NetworkPageCharacteristic(dbus.service.Object):
        """Characteristic for reading specific pages of WiFi networks"""
        
        def __init__(self, bus, index, service):
            self.path = f'{service.path}/char{index}'
            self.bus = bus
            self.service = service
            self.uuid = BLEGATTService.NETWORK_PAGE_CHAR_UUID
            self.flags = ['read', 'write']  # Write to set page number, read to get page data
            self.current_page = 0
            
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        def get_properties(self):
            return {
                'org.bluez.GattCharacteristic1': {
                    'UUID': self.uuid,
                    'Service': self.service.get_path(),
                    'Flags': self.flags
                }
            }
        
        @dbus.service.method('org.bluez.GattCharacteristic1', in_signature='aya{sv}')
        def WriteValue(self, value, options):
            """Write page number to request"""
            try:
                page_data = bytes(value).decode('utf-8')
                self.current_page = int(page_data)
                logger.info(f"📄 Client requested page {self.current_page}")
            except (ValueError, UnicodeDecodeError) as e:
                logger.error(f"❌ Invalid page number: {e}")
                self.current_page = 0
        
        @dbus.service.method('org.bluez.GattCharacteristic1', out_signature='ay')
        def ReadValue(self, options):
            """Read current page of networks"""
            logger.info(f"📡 Client reading networks page {self.current_page}")
            
            # Get the requested page
            page_data = self.service.get_networks_page(self.current_page)
            
            # Create compact JSON response
            response = json.dumps(page_data, separators=(',', ':'))
            logger.info(f"📤 Sending page {self.current_page}: {len(page_data['networks'])} networks ({len(response)} bytes)")
            
            # Ensure response fits in BLE characteristic
            if len(response) > 400:
                # Further limit networks per page if needed
                limited_data = {
                    'networks': page_data['networks'][:3],
                    'page': page_data['page'],
                    'per_page': 3,
                    'total_pages': page_data['total_pages'],
                    'total_networks': page_data['total_networks'],
                    'has_next': (self.current_page * 3 + 3) < page_data['total_networks'],
                    'has_prev': self.current_page > 0
                }
                response = json.dumps(limited_data, separators=(',', ':'))
                logger.warning(f"📦 Page response too large, limited to 3 networks ({len(response)} bytes)")
            
            return [dbus.Byte(c) for c in response.encode('utf-8')]
        
        @dbus.service.method('org.freedesktop.DBus.Properties',
                             in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface):
            if interface != 'org.bluez.GattCharacteristic1':
                raise dbus.exceptions.DBusException('Invalid interface')
            return self.get_properties()['org.bluez.GattCharacteristic1']
    
def main():
    """Main entry point"""
    logger.info("🚀 Starting SMASH BLE WiFi Onboarding Service")

    if not DBUS_AVAILABLE:
        logger.error("❌ D-Bus libraries not available. Please ensure python3-dbus is installed.")
        return 1

    # Initialize WiFi controller and BLE service
    wifi_controller = WiFiController()
    ble_service = BLEGATTService(wifi_controller)

    # Check if we're in auto-reconnection mode
    auto_reconnect = os.getenv('WIFI_AUTO_RECONNECT', 'false').lower() == 'true'

    if auto_reconnect:
        logger.info("🔄 Auto-reconnection mode detected")
        # Handle Wi-Fi auto-reconnection
        config = wifi_controller.load_saved_config()

        if config and config.get('ssid'):
            logger.info(f"🔄 Attempting auto-reconnection to: {config['ssid']}")
            set_led_status('wifi_connecting')  # Solid red during reconnection

            # Attempt connection with persistent retry
            max_attempts = 10
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Connection attempt {attempt}/{max_attempts}")

                result = wifi_controller.connect_to_network(
                    config['ssid'],
                    config.get('password', '')
                )

                if result.get('status') == 'connected':
                    logger.info("✅ Auto-reconnection successful")
                    set_led_status('wifi_connected')
                    break
                else:
                    logger.warning(f"Attempt {attempt} failed: {result.get('message', 'Unknown error')}")
                    if attempt < max_attempts:
                        time.sleep(10)  # Wait before retry
            else:
                logger.error("❌ Auto-reconnection failed - starting fresh setup")
                set_led_status('ble_advertising')  # Fall back to BLE advertising
        else:
            logger.warning("No valid saved config for auto-reconnection")
            set_led_status('ble_advertising')
    else:
        logger.info("🚀 Fresh setup mode - starting BLE advertising")
        set_led_status('ble_advertising')  # Blinking red for fresh setup
    
    # Set up signal handlers
    def signal_handler(signum, frame):
        logger.info("📴 Received shutdown signal, stopping service...")
        set_led_status('shutdown')
        sys.exit(0)
    
    def wifi_reset_handler(signum, frame):
        """Handle WiFi reset signal from button monitor"""
        logger.info("🔄 Received WiFi reset signal from button monitor")
        try:
            # Reset WiFi state in BLE service
            if hasattr(ble_service, 'service_manager') and ble_service.service_manager:
                ble_service.service_manager.current_status = {
                    'status': 'ready',
                    'message': 'Ready for WiFi configuration after reset'
                }
                logger.info("✅ BLE service WiFi state reset")

            logger.info("📱 BLE service ready for new WiFi configuration")
            # Reset LED to blinking red after reset (no network)
            set_led_status('booting')  # Blinking red - back to setup mode

        except Exception as e:
            logger.error(f"❌ Error handling WiFi reset: {e}")

    def factory_reset_handler(signum, frame):
        """Handle factory reset signal from button monitor"""
        logger.info("🚨 FACTORY RESET SIGNAL RECEIVED from button monitor")
        try:
            # Reset WiFi state in BLE service
            if hasattr(ble_service, 'service_manager') and ble_service.service_manager:
                ble_service.service_manager.current_status = {
                    'status': 'ready',
                    'message': 'Ready for WiFi configuration after factory reset'
                }
                logger.info("✅ BLE service WiFi state reset for factory reset")

            # CRITICAL: Restart BLE advertising after factory reset
            logger.info("📡 FACTORY RESET: Restarting BLE advertising...")
            ble_service.restart_advertising_after_factory_reset()

            logger.info("🔄 FACTORY RESET: Fresh boot sequence initiated")
            logger.info("📱 BLE service ready for fresh WiFi onboarding")
            # Reset LED to blinking red after factory reset (fresh boot state)
            set_led_status('booting')  # Blinking red - fresh boot, ready for setup

        except Exception as e:
            logger.error(f"❌ Error handling factory reset: {e}")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGUSR1, wifi_reset_handler)  # WiFi reset signal
    signal.signal(signal.SIGUSR2, factory_reset_handler)  # Factory reset signal
    
    # Start background network monitoring for LED updates and Ethernet IP persistence
    def network_monitor():
        """Background thread to monitor network status and update LEDs"""
        ethernet_last_status = {'connected': False, 'ip': None}
        
        # FIXED: Start network monitoring immediately for consistent LED behavior
        time.sleep(1)  # Minimal delay for system initialization
        logger.info("🔍 Starting network monitoring immediately...")
        
        while True:
            try:
                time.sleep(0.5)  # Check every 0.5 seconds for INSTANT LED transitions
                
                # Check for Ethernet reconnection and IP changes
                current_eth_status = ble_service.wifi_controller._check_ethernet_connection()
                
                # Detect Ethernet reconnection
                if not ethernet_last_status['connected'] and current_eth_status['connected']:
                    logger.info("🔌 Ethernet reconnection detected!")

                    # CRITICAL FIX: Setup dual network access when Ethernet is plugged in
                    if current_eth_status['ip']:
                        logger.info(f"🌐 ETHERNET PLUGGED IN: Setting up dual network access")
                        logger.info(f"🎯 Making Ethernet immediately accessible at: http://{current_eth_status['ip']}:8123")

                        # CRITICAL FIX: Force Home Assistant to bind to new Ethernet IP
                        logger.info("🔧 CRITICAL FIX: Configuring Home Assistant for Ethernet IP access...")
                        ha_config_success = _configure_home_assistant_ethernet_access(current_eth_status)

                        if ha_config_success:
                            logger.info("✅ Home Assistant successfully configured for Ethernet IP access")
                        else:
                            logger.warning("⚠️ Home Assistant configuration for Ethernet IP may need manual intervention")

                        # SCENARIO 2 DEBUG: Enhanced WiFi detection
                        logger.info("🔍 SCENARIO 2 DEBUG: Checking WiFi status when Ethernet plugged in...")
                        wifi_connected = False
                        wifi_ip = None
                        wifi_gateway = None

                        try:
                            wifi_check = subprocess.run(['ip', 'addr', 'show', 'wlan0'], capture_output=True, text=True)
                            logger.info(f"🔍 WiFi interface check result: {wifi_check.returncode}")
                            logger.info(f"🔍 WiFi interface output: {wifi_check.stdout[:200]}...")

                            if wifi_check.returncode == 0 and 'inet ' in wifi_check.stdout:
                                # Extract WiFi IP
                                wifi_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', wifi_check.stdout)
                                if wifi_match:
                                    wifi_ip = wifi_match.group(1)
                                    wifi_connected = True
                                    logger.info(f"✅ SCENARIO 2: WiFi IP detected: {wifi_ip}")

                                    # Get WiFi gateway
                                    route_check = subprocess.run(['ip', 'route', 'show', 'dev', 'wlan0'], capture_output=True, text=True)
                                    logger.info(f"🔍 WiFi route check: {route_check.stdout[:200]}...")

                                    for line in route_check.stdout.split('\n'):
                                        if 'default' in line and 'via' in line:
                                            parts = line.split()
                                            if 'via' in parts:
                                                gateway_idx = parts.index('via') + 1
                                                if gateway_idx < len(parts):
                                                    wifi_gateway = parts[gateway_idx]
                                                    logger.info(f"✅ SCENARIO 2: WiFi gateway detected: {wifi_gateway}")
                                                    break

                                    # Fallback: derive gateway from WiFi IP
                                    if not wifi_gateway and wifi_ip:
                                        ip_parts = wifi_ip.split('.')
                                        wifi_gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"
                                        logger.info(f"🔧 SCENARIO 2: WiFi gateway derived: {wifi_gateway}")
                                else:
                                    logger.warning("⚠️ SCENARIO 2: WiFi interface up but no IP found")
                            else:
                                logger.warning("⚠️ SCENARIO 2: WiFi interface not found or down")
                        except Exception as e:
                            logger.error(f"❌ SCENARIO 2: WiFi check error: {e}")

                        logger.info(f"🔍 SCENARIO 2 STATUS: WiFi connected={wifi_connected}, IP={wifi_ip}, Gateway={wifi_gateway}")

                        if wifi_connected and wifi_ip and wifi_gateway:
                            logger.info(f"🌐 SCENARIO 2: DUAL NETWORK DETECTED: WiFi {wifi_ip} + Ethernet {current_eth_status['ip']}")

                            # CRITICAL: Use the existing dual network routing function with enhanced error handling
                            try:
                                logger.info("🔧 SCENARIO 2: Creating WiFiController instance for dual network setup...")
                                wifi_controller = WiFiController()

                                logger.info("🔧 SCENARIO 2: Calling _setup_dual_network_routing...")
                                result = wifi_controller._setup_dual_network_routing(
                                    wifi_ip=wifi_ip,
                                    wifi_gateway=wifi_gateway,
                                    is_static=True
                                )

                                if result is not False:  # Function may return None on success
                                    logger.info("✅ SCENARIO 2: Dual network access configured - BOTH IPs now accessible!")
                                else:
                                    logger.error("❌ SCENARIO 2: Dual network routing returned False")

                            except Exception as e:
                                logger.error(f"❌ SCENARIO 2: Failed to setup dual network routing: {e}")
                                logger.error(f"❌ SCENARIO 2: Exception type: {type(e).__name__}")
                                import traceback
                                logger.error(f"❌ SCENARIO 2: Traceback: {traceback.format_exc()}")

                                # Fallback: basic Ethernet setup
                                logger.info("🔧 SCENARIO 2: Falling back to basic Ethernet setup...")
                                _setup_basic_ethernet_access(current_eth_status)
                        else:
                            logger.info("🔧 SCENARIO 2: WiFi not connected - setting up Ethernet-only access")
                            _setup_basic_ethernet_access(current_eth_status)
                
                # Detect Ethernet IP change
                elif (ethernet_last_status['connected'] and current_eth_status['connected'] and 
                      ethernet_last_status['ip'] != current_eth_status['ip']):
                    logger.warning(f"⚠️ Ethernet IP changed: {ethernet_last_status['ip']} -> {current_eth_status['ip']}")
                    if current_eth_status['ip']:
                        logger.info(f"🎯 Ethernet now accessible at: http://{current_eth_status['ip']}:8123")
                
                # Update tracking
                ethernet_last_status = current_eth_status.copy()
                
                # Update LED status based on current network state
                update_network_led_status()
                
            except Exception as e:
                logger.debug(f"Network monitor error: {e}")
                time.sleep(2)  # Wait shorter on error for FASTER responsiveness
    
    # CRITICAL FIX: Check and configure Home Assistant for all available IPs at startup
    logger.info("🔧 STARTUP FIX: Checking Home Assistant IP binding configuration...")
    try:
        # Check if Ethernet is available at startup
        eth_status = ble_service.wifi_controller._check_ethernet_connection()
        if eth_status['connected'] and eth_status['ip']:
            logger.info(f"🌐 Ethernet detected at startup: {eth_status['ip']}")
            logger.info("🔧 Configuring Home Assistant for Ethernet IP access at startup...")
            _configure_home_assistant_ethernet_access(eth_status)

        # Check if WiFi is available at startup
        wifi_check = subprocess.run(['ip', 'addr', 'show', 'wlan0'], capture_output=True, text=True)
        if wifi_check.returncode == 0 and 'inet ' in wifi_check.stdout:
            wifi_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', wifi_check.stdout)
            if wifi_match:
                wifi_ip = wifi_match.group(1)
                logger.info(f"🌐 WiFi detected at startup: {wifi_ip}")
                logger.info("✅ WiFi IP should already be accessible for Home Assistant")

        logger.info("✅ Startup IP configuration check completed")

    except Exception as e:
        logger.warning(f"⚠️ Startup IP configuration check failed: {e}")

    # IMMEDIATE LED STATUS UPDATE - Set correct status from startup
    logger.info("🚥 Setting initial LED status...")
    update_network_led_status()  # This will set correct LED status immediately

    import threading
    monitor_thread = threading.Thread(target=network_monitor, daemon=True)
    monitor_thread.start()
    logger.info("🔍 Network monitoring started immediately for consistent LED behavior")

    # Start the BLE service FIRST - without waiting for network status
    logger.info("📡 Starting BLE GATT service for WiFi onboarding...")
    success = ble_service.start_service()
    
    return 0 if success else 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
