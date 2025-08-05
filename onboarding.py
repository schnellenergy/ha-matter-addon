#!/usr/bin/env python3
"""
Complete Working WiFi Onboarding Solution
- Creates hotspot using run.sh approach (WORKS)
- Actually connects to WiFi with proper DHCP (FIXED)
- Handles all edge cases and recovery paths
- Uses wpa_supplicant + dhclient for Home Assistant OS compatibility
"""

from flask import Flask, request, render_template_string, jsonify
import os
import json
import logging
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)


class WorkingWiFiController:
    def __init__(self):
        self.config_file = "/data/wifi_config.json"
        self.hotspot_ssid = os.getenv('HOTSPOT_SSID', 'WiFi-Setup')
        self.current_mode = "hotspot"  # Start in hotspot mode
        self.wpa_supplicant_proc = None
        self.dhcp_proc = None
        self.connection_timeout = int(os.getenv('CONNECTION_TIMEOUT', '60'))

        # Static IP configuration from addon options
        self.use_static_ip = os.getenv(
            'USE_STATIC_IP', 'false').lower() == 'true'
        self.static_ip = os.getenv('STATIC_IP', '192.168.1.100')
        self.static_gateway = os.getenv('STATIC_GATEWAY', '192.168.1.1')
        self.static_dns = os.getenv('STATIC_DNS', '8.8.8.8')

        # Dual network configuration
        self.dual_network = os.getenv('DUAL_NETWORK', 'true').lower() == 'true'
        
        # Enhanced Network Management with Ethernet Priority
        self.ethernet_monitoring_started = False
        self.ip_state_file = "/tmp/ip_state.json"
        self.shared_ip = None
        self.active_interface = None  # 'ethernet' or 'wifi'
        self.reserved_ip = None
        self.ethernet_interfaces = ['end0', 'eth0', 'enp0s3']
        
        # Button reset tracking for debugging
        self.reset_count = 0
        self.last_reset_time = 0
        
        # Load previous IP state if exists
        self.load_ip_state()

    def load_ip_state(self):
        """Load IP sharing state from persistent storage"""
        try:
            if os.path.exists(self.ip_state_file):
                with open(self.ip_state_file, 'r') as f:
                    state = json.load(f)
                    self.shared_ip = state.get('shared_ip')
                    self.active_interface = state.get('active_interface')
                    self.reserved_ip = state.get('reserved_ip')
                    logger.info(f"📊 Loaded IP state: shared_ip={self.shared_ip}, active={self.active_interface}")
        except Exception as e:
            logger.debug(f"Failed to load IP state: {e}")
            self.shared_ip = None
            self.active_interface = None
            self.reserved_ip = None
    
    def save_ip_state(self):
        """Save IP sharing state to persistent storage"""
        try:
            state = {
                'shared_ip': self.shared_ip,
                'active_interface': self.active_interface,
                'reserved_ip': self.reserved_ip,
                'timestamp': time.time()
            }
            os.makedirs(os.path.dirname(self.ip_state_file), exist_ok=True)
            with open(self.ip_state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"💾 Saved IP state: shared_ip={self.shared_ip}, active={self.active_interface}")
        except Exception as e:
            logger.warning(f"Failed to save IP state: {e}")
    
    def get_interface_ip(self, interface):
        """Get current IP address of an interface"""
        try:
            result = self.run_command(["ip", "addr", "show", interface], log_output=False)
            if result and result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'inet ' in line and 'scope global' in line:
                        return line.strip().split()[1].split('/')[0]
        except Exception as e:
            logger.debug(f"Failed to get IP for {interface}: {e}")
        return None
    
    def set_interface_ip(self, interface, ip_cidr, gateway=None):
        """Set IP address on interface with comprehensive cleanup"""
        try:
            ip_only = ip_cidr.split('/')[0]
            
            # Step 1: Aggressive cleanup of existing IPs
            logger.info(f"🧩 Cleaning all IPs from {interface}")
            
            # Kill any DHCP clients that might be managing this interface
            for dhcp_client in ["dhcpcd", "dhclient", "udhcpc"]:
                self.run_command(["pkill", "-f", f"{dhcp_client}.*{interface}"], log_output=False)
            
            # Flush all addresses from interface
            self.run_command(["ip", "addr", "flush", "dev", interface], log_output=False)
            time.sleep(1)
            
            # Double-check: remove any lingering routes
            self.run_command(["ip", "route", "flush", "dev", interface], log_output=False)
            
            # Step 2: Add the new IP
            result = self.run_command(["ip", "addr", "add", ip_cidr, "dev", interface])
            if result and result.returncode == 0:
                logger.info(f"🌐 Assigned {ip_cidr} to {interface}")
                
                # Step 3: Add gateway if provided
                if gateway:
                    # Remove existing default routes that might conflict
                    self.run_command(["ip", "route", "del", "default"], log_output=False)
                    time.sleep(1)
                    
                    # Add new default route
                    route_result = self.run_command(["ip", "route", "add", "default", "via", gateway, "dev", interface])
                    if route_result and route_result.returncode == 0:
                        logger.info(f"🛣️ Added default route via {gateway}")
                    else:
                        logger.warning(f"⚠️ Failed to add default route via {gateway}")
                
                time.sleep(2)  # Allow network stack to stabilize
                return True
            else:
                logger.error(f"❌ Failed to assign {ip_cidr} to {interface}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to set interface IP: {e}")
            return False

    def run_command(self, cmd, timeout=30, log_output=True):
        """Run shell command safely"""
        try:
            if log_output:
                logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, timeout=timeout, capture_output=True, text=True)
            if result.returncode != 0 and result.stderr and log_output:
                logger.warning(f"Command stderr: {result.stderr}")
            return result
        except Exception as e:
            if log_output:
                logger.error(f"Command failed: {e}")
            return None

    def stop_all_network_services(self):
        """Stop all network services with improved service management"""
        logger.info("🛑 Stopping all network services...")

        # First try systemctl for managed services
        systemctl_services = [
            "hostapd", "dnsmasq", "wpa_supplicant", "dhcpcd"
        ]

        for service in systemctl_services:
            try:
                # Try to stop systemd service first
                result = self.run_command(
                    ["systemctl", "stop", service], log_output=False)
                if result and result.returncode == 0:
                    logger.debug(f"Stopped systemd service: {service}")
                time.sleep(0.5)
            except:
                pass

        # Then kill any remaining processes
        processes_to_kill = [
            "hostapd", "dnsmasq", "wpa_supplicant",
            "dhcpcd", "udhcpc", "dhclient"
        ]

        for process in processes_to_kill:
            try:
                # Try SIGTERM first (graceful)
                self.run_command(
                    ["pkill", "-TERM", "-f", process], log_output=False)
                time.sleep(1)
                # Then SIGKILL if still running (force)
                self.run_command(
                    ["pkill", "-KILL", "-f", process], log_output=False)
                time.sleep(0.5)
            except:
                pass

        # Clean up any lingering processes
        if self.wpa_supplicant_proc:
            try:
                self.wpa_supplicant_proc.terminate()
                self.wpa_supplicant_proc.wait(timeout=5)
            except:
                pass
            self.wpa_supplicant_proc = None

        if self.dhcp_proc:
            try:
                self.dhcp_proc.terminate()
                self.dhcp_proc.wait(timeout=5)
            except:
                pass
            self.dhcp_proc = None

    def reset_interface(self):
        """Reset wlan0 interface completely with enhanced recovery"""
        logger.info("🔄 Resetting interface for client mode...")

        try:
            # First check if interface exists
            result = self.run_command(
                ["ip", "link", "show", "wlan0"], log_output=False)
            if not result or result.returncode != 0:
                logger.error("wlan0 interface not found")
                return False

            # Bring interface down
            self.run_command(["ip", "link", "set", "wlan0", "down"])
            time.sleep(2)

            # Kill any processes using the interface
            self.run_command(["pkill", "-f", "wlan0"], log_output=False)
            time.sleep(1)

            # Flush all addresses and routes
            self.run_command(["ip", "addr", "flush", "dev", "wlan0"])
            time.sleep(1)
            self.run_command(["ip", "route", "flush", "dev",
                             "wlan0"], log_output=False)
            time.sleep(1)

            # Remove any wireless configuration
            self.run_command(
                ["iw", "dev", "wlan0", "disconnect"], log_output=False)
            time.sleep(1)

            # Bring interface back up
            self.run_command(["ip", "link", "set", "wlan0", "up"])
            time.sleep(3)  # Give more time for interface to come up

            # Verify interface is up
            result = self.run_command(
                ["ip", "link", "show", "wlan0"], log_output=False)
            if result and "UP" in result.stdout:
                logger.info("✅ Interface reset complete")
                return True
            else:
                logger.error("Interface failed to come up after reset")
                return False

        except Exception as e:
            logger.error(f"Interface reset failed: {e}")
            return False

    def create_wpa_config(self, ssid, password):
        """Create enhanced wpa_supplicant configuration"""
        logger.info(f"📝 Creating wpa_supplicant config for {ssid}")

        config_content = "# WiFi Onboarding wpa_supplicant configuration\n"
        config_content += "ctrl_interface=/var/run/wpa_supplicant\n"
        config_content += "ctrl_interface_group=0\n"
        config_content += "update_config=1\n"
        config_content += "country=US\n"
        config_content += "ap_scan=1\n"
        config_content += "fast_reauth=1\n\n"

        if password:
            # WPA/WPA2/WPA3 encrypted network with better compatibility
            config_content += "network={\n"
            config_content += f'    ssid="{ssid}"\n'
            config_content += f'    psk="{password}"\n'
            config_content += "    key_mgmt=WPA-PSK WPA-EAP\n"  # Support both PSK and EAP
            config_content += "    proto=RSN WPA\n"  # Support both WPA2 and WPA
            config_content += "    pairwise=CCMP TKIP\n"  # Support both encryption types
            config_content += "    group=CCMP TKIP\n"
            config_content += "    priority=5\n"
            config_content += "    scan_ssid=1\n"  # Actively scan for hidden networks
            config_content += "}\n"
        else:
            # Open network
            config_content += "network={\n"
            config_content += f'    ssid="{ssid}"\n'
            config_content += "    key_mgmt=NONE\n"
            config_content += "    priority=5\n"
            config_content += "    scan_ssid=1\n"
            config_content += "}\n"

        try:
            with open("/tmp/wpa_supplicant.conf", "w") as f:
                f.write(config_content)
            logger.info("✅ wpa_supplicant config created")
            logger.debug(f"Config content:\n{config_content}")
            return True
        except Exception as e:
            logger.error(f"Failed to create wpa config: {e}")
            return False

    def start_wpa_supplicant(self):
        """Start wpa_supplicant in background"""
        logger.info("🔗 Starting wpa_supplicant...")

        try:
            # Kill any existing wpa_supplicant
            self.run_command(
                ["pkill", "-f", "wpa_supplicant"], log_output=False)
            time.sleep(2)

            # Start wpa_supplicant
            cmd = [
                "wpa_supplicant",
                "-B",  # Run in background
                "-i", "wlan0",
                "-c", "/tmp/wpa_supplicant.conf",
                "-D", "nl80211"
            ]

            result = self.run_command(cmd, timeout=10)
            if result and result.returncode == 0:
                logger.info("✅ wpa_supplicant started")
                return True
            else:
                logger.error("❌ wpa_supplicant failed to start")
                return False

        except Exception as e:
            logger.error(f"wpa_supplicant start failed: {e}")
            return False

    def wait_for_association(self, timeout=45):
        """Wait for WiFi association with enhanced debugging"""
        logger.info("⏳ Waiting for WiFi association...")

        # First, trigger a scan to find networks
        logger.info("🔍 Triggering network scan...")
        scan_cmd = self.run_command(
            ["wpa_cli", "-i", "wlan0", "scan"], log_output=False)
        time.sleep(5)  # Wait for scan to complete

        start_time = time.time()
        last_state = ""
        scan_done = False

        while time.time() - start_time < timeout:
            try:
                # Check wpa_supplicant status
                result = self.run_command([
                    "wpa_cli", "-i", "wlan0", "status"
                ], log_output=False)

                if result and result.returncode == 0:
                    # Log full status for debugging
                    logger.debug(f"wpa_cli status output:\n{result.stdout}")

                    current_state = ""
                    for line in result.stdout.split('\n'):
                        if line.startswith('wpa_state='):
                            current_state = line.strip()
                            break

                    # Only log state changes to avoid spam
                    if current_state != last_state:
                        logger.info(f"📡 WiFi state: {current_state}")
                        last_state = current_state

                    if "wpa_state=COMPLETED" in result.stdout:
                        logger.info("✅ WiFi association successful")

                        # Also log the network info
                        for line in result.stdout.split('\n'):
                            if line.startswith('ssid='):
                                logger.info(
                                    f"📶 Connected to: {line.split('=', 1)[1]}")
                            elif line.startswith('ip_address='):
                                logger.info(
                                    f"🌐 IP assigned: {line.split('=', 1)[1]}")

                        return True
                    elif "wpa_state=SCANNING" in result.stdout:
                        if not scan_done:
                            logger.info("🔍 Scanning for networks...")
                            scan_done = True
                    elif "wpa_state=ASSOCIATING" in result.stdout:
                        logger.info("🔗 Associating with network...")
                    elif "wpa_state=4WAY_HANDSHAKE" in result.stdout:
                        logger.info("🔐 Performing authentication handshake...")
                    elif "wpa_state=DISCONNECTED" in result.stdout:
                        # First time seeing disconnected, do scan and analysis
                        if not scan_done:
                            logger.warning(
                                "❌ Connection failed - performing network scan...")

                            # Trigger a fresh scan
                            self.run_command(
                                ["wpa_cli", "-i", "wlan0", "scan"], log_output=False)
                            time.sleep(5)

                            # Get scan results
                            scan_result = self.run_command([
                                "wpa_cli", "-i", "wlan0", "scan_results"
                            ], log_output=False)

                            if scan_result and scan_result.returncode == 0:
                                logger.debug(
                                    f"Scan results:\n{scan_result.stdout}")

                                # Check if our network is visible
                                config = self.load_config()
                                if config:
                                    ssid = config.get('ssid', '')
                                    if ssid in scan_result.stdout:
                                        logger.warning(
                                            f"⚠️ Network '{ssid}' found, trying to connect...")
                                        # Try to reconnect
                                        self.run_command(
                                            ["wpa_cli", "-i", "wlan0", "reconnect"], log_output=False)
                                    else:
                                        logger.error(
                                            f"❌ Network '{ssid}' not found in scan results")
                                        logger.info("Available networks:")
                                        # Skip header
                                        for line in scan_result.stdout.split('\n')[1:]:
                                            if line.strip():
                                                parts = line.split('\t')
                                                if len(parts) >= 5:
                                                    network_ssid = parts[4]
                                                    signal = parts[2]
                                                    logger.info(
                                                        f"  - {network_ssid} (signal: {signal})")

                            scan_done = True

                        # If we've been disconnected for too long, give up
                        if time.time() - start_time > 15:  # 15 seconds in disconnected state
                            logger.error("❌ Remained disconnected too long")
                            return False
                    elif "wpa_state=INACTIVE" in result.stdout:
                        logger.warning(
                            "⚠️ wpa_supplicant inactive - trying to restart...")
                        self.run_command(
                            ["wpa_cli", "-i", "wlan0", "reconnect"], log_output=False)

                time.sleep(3)  # Longer sleep for better stability

            except Exception as e:
                logger.debug(f"Association check failed: {e}")
                time.sleep(3)

        logger.error("❌ WiFi association timeout")
        return False

    def configure_static_ip(self):
        """Configure static IP address on wlan0"""
        logger.info(f"🔹 Configuring static IP: {self.static_ip}")

        try:
            # Remove any existing IP addresses
            self.run_command(["ip", "addr", "flush", "dev", "wlan0"])
            time.sleep(1)

            # Add static IP address
            cidr = f"{self.static_ip}/24"  # Assume /24 subnet
            result = self.run_command(
                ["ip", "addr", "add", cidr, "dev", "wlan0"])
            if result and result.returncode == 0:
                logger.info(f"✅ Static IP {self.static_ip} configured")
            else:
                logger.error(
                    f"❌ Failed to configure static IP {self.static_ip}")
                return False

            # Add default route via gateway
            # Remove existing default route
            self.run_command(
                ["ip", "route", "del", "default"], log_output=False)
            result = self.run_command(
                ["ip", "route", "add", "default", "via", self.static_gateway, "dev", "wlan0"])
            if result and result.returncode == 0:
                logger.info(
                    f"✅ Default route via {self.static_gateway} configured")
            else:
                logger.error(
                    f"❌ Failed to configure default route via {self.static_gateway}")
                return False

            # Configure DNS
            dns_content = f"nameserver {self.static_dns}\nnameserver 8.8.4.4\n"
            try:
                with open("/etc/resolv.conf", "w") as f:
                    f.write(dns_content)
                logger.info(f"✅ DNS configured: {self.static_dns}")
            except Exception as e:
                logger.warning(f"Failed to configure DNS: {e}")

            time.sleep(3)  # Give network stack time to stabilize
            return True

        except Exception as e:
            logger.error(f"Static IP configuration failed: {e}")
            return False

    def start_dhcp_client(self):
        """Start DHCP client with multiple fallback methods or configure static IP"""

        # Check if static IP is configured
        if self.use_static_ip:
            logger.info("🔹 Using static IP configuration")
            return self.configure_static_ip()

        logger.info("🌐 Starting DHCP client...")

        try:
            # Kill any existing DHCP clients on wlan0
            dhcp_processes = ["dhcpcd.*wlan0",
                              "udhcpc.*wlan0", "dhclient.*wlan0"]
            for process in dhcp_processes:
                self.run_command(["pkill", "-f", process], log_output=False)
            time.sleep(2)

            # Method 1: Try dhcpcd (most reliable on modern systems)
            dhcpcd_paths = ["/sbin/dhcpcd", "/usr/sbin/dhcpcd", "/bin/dhcpcd"]
            for dhcpcd_path in dhcpcd_paths:
                if os.path.exists(dhcpcd_path):
                    logger.info(f"Using dhcpcd at {dhcpcd_path} for DHCP...")
                    cmd = [dhcpcd_path, "-4", "-t", "30", "-w", "wlan0"]
                    result = self.run_command(cmd, timeout=35)

                    if result and result.returncode == 0:
                        logger.info("✅ dhcpcd succeeded")
                        time.sleep(5)  # Give DHCP time to complete
                        return True
                    break

            # Method 2: Try dhclient (common on Ubuntu/Debian)
            dhclient_paths = ["/sbin/dhclient", "/usr/sbin/dhclient"]
            for dhclient_path in dhclient_paths:
                if os.path.exists(dhclient_path):
                    logger.info(
                        f"Using dhclient at {dhclient_path} for DHCP...")
                    cmd = [dhclient_path, "-4", "-v", "wlan0"]
                    result = self.run_command(cmd, timeout=35)

                    if result and result.returncode == 0:
                        logger.info("✅ dhclient succeeded")
                        time.sleep(5)  # Give DHCP time to complete
                        return True
                    break

            # Method 3: Try udhcpc (busybox DHCP client)
            udhcpc_paths = ["/sbin/udhcpc", "/usr/sbin/udhcpc", "/bin/udhcpc"]
            for udhcpc_path in udhcpc_paths:
                if os.path.exists(udhcpc_path):
                    logger.info(f"Using udhcpc at {udhcpc_path} for DHCP...")
                    cmd = [udhcpc_path, "-i", "wlan0", "-n", "-t", "10", "-q"]
                    result = self.run_command(cmd, timeout=35)

                    if result and result.returncode == 0:
                        logger.info("✅ udhcpc succeeded")
                        time.sleep(5)  # Give DHCP time to complete
                        return True
                    break

            # Method 4: Try NetworkManager if available
            if os.path.exists("/usr/bin/nmcli"):
                logger.info("Trying NetworkManager for DHCP...")
                # Refresh network connections
                self.run_command(
                    ["nmcli", "device", "connect", "wlan0"], log_output=False)
                time.sleep(10)

                # Check if we got an IP
                result = self.run_command(
                    ["ip", "addr", "show", "wlan0"], log_output=False)
                if result and result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if "inet " in line and "192.168.4." not in line and "127.0.0.1" not in line:
                            logger.info("✅ Got IP via NetworkManager")
                            return True

            # Method 5: Manual interface cycling (last resort)
            logger.info("Trying manual interface cycling for DHCP...")
            self.run_command(["ip", "link", "set", "wlan0", "down"])
            time.sleep(2)
            self.run_command(["ip", "link", "set", "wlan0", "up"])
            time.sleep(10)  # Give more time for automatic DHCP

            # Check if we got an IP after cycling
            result = self.run_command(
                ["ip", "addr", "show", "wlan0"], log_output=False)
            if result and result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if "inet " in line and "192.168.4." not in line and "127.0.0.1" not in line:
                        logger.info("✅ Got IP via interface cycling")
                        return True

            logger.error("❌ All DHCP methods failed")
            return False

        except Exception as e:
            logger.error(f"DHCP client failed: {e}")
            return False

    def verify_connection(self):
        """Verify we have a real IP and connectivity with enhanced checks"""
        logger.info("🔍 Verifying connection...")

        # Give DHCP more time to complete
        logger.info("⏳ Waiting for DHCP to complete...")
        time.sleep(15)  # Increased wait time

        for attempt in range(5):  # Increased attempts
            try:
                # Check for IP address (not 192.168.4.x)
                result = self.run_command(
                    ["ip", "addr", "show", "wlan0"], log_output=False)
                if result and result.returncode == 0:
                    ip_found = None
                    gateway_ip = None

                    for line in result.stdout.split('\n'):
                        if "inet " in line and "192.168.4." not in line and "127.0.0.1" not in line:
                            ip_parts = line.strip().split()
                            if len(ip_parts) > 1:
                                ip_found = ip_parts[1]
                                logger.info(f"🎉 Got IP address: {ip_found}")
                                break

                    if ip_found:
                        # Get gateway information
                        route_result = self.run_command(
                            ["ip", "route", "show", "default"], log_output=False)
                        if route_result and route_result.returncode == 0:
                            for line in route_result.stdout.split('\n'):
                                if "default via" in line and "wlan0" in line:
                                    parts = line.split()
                                    if len(parts) >= 3:
                                        gateway_ip = parts[2]
                                        logger.info(f"🌐 Gateway: {gateway_ip}")
                                        break

                        # Test local network connectivity first (ping gateway)
                        if gateway_ip:
                            logger.info(
                                f"🌐 Testing gateway connectivity: {gateway_ip}")
                            gateway_ping = self.run_command([
                                "ping", "-c", "2", "-W", "3", gateway_ip
                            ], log_output=False)

                            if gateway_ping and gateway_ping.returncode == 0:
                                logger.info("✅ Gateway connectivity confirmed")

                                # Test internet connectivity
                                logger.info(
                                    "🌍 Testing internet connectivity...")
                                internet_ping = self.run_command([
                                    "ping", "-c", "2", "-W", "5", "8.8.8.8"
                                ], log_output=False)

                                if internet_ping and internet_ping.returncode == 0:
                                    logger.info(
                                        "✅ Internet connectivity confirmed")
                                else:
                                    logger.info(
                                        "⚠️ Local network OK, limited internet")

                                return True
                            else:
                                logger.warning("❌ Gateway not reachable")
                        else:
                            # No gateway found, but we have an IP - might still work
                            logger.info("⚠️ No gateway found, but IP assigned")
                            return True

                    logger.warning(
                        f"❌ No valid IP address (attempt {attempt + 1}/5)")
                    if attempt < 4:  # Don't sleep on last attempt
                        time.sleep(8)  # Longer wait between attempts

            except Exception as e:
                logger.error(f"Connection verification failed: {e}")
                if attempt < 4:
                    time.sleep(8)

        logger.error("❌ Could not verify connection after 5 attempts")
        return False

    def connect_to_wifi(self, ssid, password):
        """Complete WiFi connection process with proper DHCP"""
        logger.info(f"📡 Connecting to WiFi: {ssid}")

        try:
            # Step 1: Stop all network services
            self.stop_all_network_services()
            time.sleep(3)

            # Step 2: Reset interface
            if not self.reset_interface():
                logger.error("❌ Interface reset failed")
                return False

            # Step 3: Create wpa_supplicant config
            if not self.create_wpa_config(ssid, password):
                logger.error("❌ Failed to create wpa config")
                return False

            # Step 4: Start wpa_supplicant
            if not self.start_wpa_supplicant():
                logger.error("❌ wpa_supplicant failed")
                return False

            # Step 5: Wait for association
            if not self.wait_for_association(timeout=30):
                logger.error("❌ WiFi association failed")
                return False

            # Step 6: Start DHCP client
            if not self.start_dhcp_client():
                logger.error("❌ DHCP failed")
                return False

            # Step 7: Verify connection
            time.sleep(5)  # Give DHCP time to complete
            if not self.verify_connection():
                logger.error("❌ Connection verification failed")
                return False

            # Step 8: Save configuration
            self.save_config(ssid, password)
            self.current_mode = "client"

            # Step 9: Manage network interface priority with enhanced Ethernet priority
            if self.dual_network:
                self.manage_enhanced_network_priority()
                # Start continuous network monitoring
                self.start_ethernet_monitoring()
            else:
                logger.info(
                    "🔧 Dual network disabled - WiFi will be primary interface")

            logger.info("🎉 SUCCESS! WiFi connection complete")
            return True

        except Exception as e:
            logger.error(f"💥 WiFi connection exception: {e}")
            return False

    def manage_interface_priority(self):
        """Configure dual network interface support - both WiFi and Ethernet accessible"""
        try:
            logger.info("🔄 Configuring dual network interface support...")

            # Get current WiFi IP
            result = self.run_command(
                ["ip", "addr", "show", "wlan0"], log_output=False)
            if result and result.returncode == 0:
                wifi_ip = None
                wifi_gateway = None
                for line in result.stdout.split('\n'):
                    if 'inet ' in line and '192.168.4.1' not in line:  # Skip hotspot IP
                        wifi_ip = line.strip().split()[1].split('/')[0]
                        break

                # Get WiFi gateway
                result = self.run_command(
                    ["ip", "route", "show", "dev", "wlan0"], log_output=False)
                if result and result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'default via' in line:
                            wifi_gateway = line.split('via')[1].split()[0]
                            break

                if wifi_ip:
                    logger.info(f"📶 WiFi active with IP: {wifi_ip}")
                    if wifi_gateway:
                        logger.info(f"📶 WiFi gateway: {wifi_gateway}")

                    # Check ethernet interfaces and configure dual access
                    eth_interfaces = ['end0', 'eth0', 'enp0s3']
                    for eth_iface in eth_interfaces:
                        result = self.run_command(
                            ["ip", "addr", "show", eth_iface], log_output=False)
                        if result and result.returncode == 0 and 'inet ' in result.stdout:
                            # Extract ethernet IP
                            eth_ip = None
                            for line in result.stdout.split('\n'):
                                if 'inet ' in line:
                                    eth_ip = line.strip().split()[
                                        1].split('/')[0]
                                    break

                            if eth_ip:
                                logger.info(
                                    f"🔌 Ethernet interface {eth_iface} active with IP: {eth_ip}")

                                # Configure dual network access - both should work
                                logger.info(
                                    "🔧 Configuring dual network access...")

                                # Ensure both interfaces have proper routing
                                # WiFi gets priority for internet, but both IPs should be accessible

                                # Add specific routes for each interface to ensure local access works
                                wifi_network = '.'.join(
                                    wifi_ip.split('.')[:-1]) + '.0/24'
                                eth_network = '.'.join(
                                    eth_ip.split('.')[:-1]) + '.0/24'

                                # Ensure local network routes exist for both interfaces
                                self.run_command(
                                    ["ip", "route", "add", wifi_network, "dev", "wlan0"], log_output=False)
                                self.run_command(
                                    ["ip", "route", "add", eth_network, "dev", eth_iface], log_output=False)

                                logger.info(f"✅ Dual network configured:")
                                logger.info(
                                    f"   📶 WiFi: {wifi_ip} (primary for internet)")
                                logger.info(
                                    f"   🔌 Ethernet: {eth_ip} (secondary, local access)")
                                logger.info(
                                    f"   🌐 Both IPs should be accessible for Home Assistant")
                                break

                    # Show final network status
                    logger.info("📊 Final network configuration:")
                    result = self.run_command(
                        ["ip", "route", "show"], log_output=False)
                    if result and result.returncode == 0:
                        routes = result.stdout.strip()
                        logger.info(
                            f"   Active routes: {len(routes.split(chr(10)))} routes configured")
                        # Log first few routes for debugging
                        for i, route in enumerate(routes.split('\n')[:3]):
                            if route.strip():
                                logger.info(f"   Route {i+1}: {route.strip()}")

                    # Test both interfaces
                    logger.info("🧪 Testing network interface accessibility...")
                    if wifi_ip:
                        logger.info(
                            f"   📶 WiFi should be accessible at: http://{wifi_ip}:8123/")

                    # Check if ethernet is available for testing
                    for eth_iface in eth_interfaces:
                        result = self.run_command(
                            ["ip", "addr", "show", eth_iface], log_output=False)
                        if result and result.returncode == 0 and 'inet ' in result.stdout:
                            for line in result.stdout.split('\n'):
                                if 'inet ' in line:
                                    eth_ip = line.strip().split()[
                                        1].split('/')[0]
                                    logger.info(
                                        f"   🔌 Ethernet should be accessible at: http://{eth_ip}:8123/")
                                    break
                            break

        except Exception as e:
            logger.warning(f"Failed to configure dual network support: {e}")

    def manage_enhanced_network_priority(self):
        """Enhanced network priority management - ETHERNET ALWAYS WINS"""
        logger.info("🔄 Managing enhanced network priority system - ETHERNET FIRST!")
        
        # Detect current network states
        ethernet_info = self.detect_ethernet_connection()
        wifi_ip = self.get_interface_ip('wlan0')
        
        # Filter out hotspot IP from WiFi
        if wifi_ip and wifi_ip.startswith('192.168.4.'):
            wifi_ip = None
        
        logger.info(f"📊 Network State: Ethernet={ethernet_info}, WiFi_IP={wifi_ip}, Active={self.active_interface}")
        
        # ABSOLUTE PRIORITY LOGIC: ETHERNET > WIFI
        if ethernet_info and ethernet_info['connected']:
            # ETHERNET CONNECTED = HIGHEST PRIORITY ALWAYS
            logger.info("🔌 ETHERNET DETECTED - TAKING ABSOLUTE PRIORITY")
            self.handle_ethernet_priority(ethernet_info, wifi_ip)
        elif wifi_ip:
            # WIFI ONLY USED WHEN ETHERNET NOT AVAILABLE
            logger.info("📶 No ethernet - WiFi fallback mode")
            self.handle_wifi_fallback(wifi_ip)
        else:
            # NO NETWORK CONNECTION
            logger.info("❌ No network connections available")
            self.handle_no_network_connection()
    
    def detect_ethernet_connection(self):
        """Detect if ethernet is connected and get its details"""
        ethernet_info = None
        
        for eth_iface in self.ethernet_interfaces:
            try:
                # Check if interface exists and is up
                result = self.run_command(["ip", "link", "show", eth_iface], log_output=False)
                if result and result.returncode == 0 and 'state UP' in result.stdout:
                    # Check if it has carrier (cable connected)
                    carrier_file = f"/sys/class/net/{eth_iface}/carrier"
                    if os.path.exists(carrier_file):
                        with open(carrier_file, 'r') as f:
                            if f.read().strip() == '1':
                                # Ethernet is physically connected
                                current_ip = self.get_interface_ip(eth_iface)
                                ethernet_info = {
                                    'interface': eth_iface,
                                    'ip': current_ip,
                                    'connected': True
                                }
                                logger.debug(f"🔌 Ethernet detected: {eth_iface} with IP {current_ip}")
                                break
            except Exception as e:
                logger.debug(f"Error checking ethernet {eth_iface}: {e}")
                continue
        
        return ethernet_info
    
    def handle_ethernet_priority(self, ethernet_info, wifi_ip):
        """Handle ethernet priority scenarios - ETHERNET ALWAYS WINS"""
        eth_iface = ethernet_info['interface']
        eth_current_ip = ethernet_info['ip']
        
        logger.info(f"🔌 ETHERNET PRIORITY: Processing ethernet connection on {eth_iface}")
        
        if eth_current_ip:
            # Ethernet already has IP - this takes absolute priority
            logger.info(f"🎯 ETHERNET HAS IP: {eth_current_ip} - Setting as active interface")
            self.active_interface = 'ethernet'
            self.shared_ip = eth_current_ip  # Always use ethernet IP as reference
            
            # Don't remove WiFi IP - just ensure ethernet has priority in routing
            if wifi_ip:
                logger.info(f"📶 WiFi IP {wifi_ip} detected, but ethernet {eth_current_ip} has priority")
                # Set ethernet as default route with higher priority
                self.set_ethernet_as_default_route(eth_iface, eth_current_ip)
            
            logger.info(f"✅ ETHERNET ACTIVE: {eth_current_ip} on {eth_iface} (PRIMARY)")
                
        else:
            # Ethernet connected but no IP - get one immediately
            logger.info(f"🔌 Ethernet connected but no IP - getting DHCP on {eth_iface}")
            
            # Try to get IP via DHCP
            if self.get_dhcp_ip_for_interface(eth_iface):
                time.sleep(2)  # Allow DHCP to complete
                new_eth_ip = self.get_interface_ip(eth_iface)
                if new_eth_ip:
                    logger.info(f"✅ Ethernet got IP: {new_eth_ip}")
                    self.active_interface = 'ethernet'
                    self.shared_ip = new_eth_ip
                    
                    # Set ethernet as default route
                    self.set_ethernet_as_default_route(eth_iface, new_eth_ip)
                    logger.info(f"🎯 ETHERNET NOW ACTIVE: {new_eth_ip} on {eth_iface} (PRIMARY)")
                else:
                    logger.warning(f"❌ Failed to get IP for ethernet {eth_iface}")
        
        self.save_ip_state()
    
    def set_ethernet_as_default_route(self, eth_iface, eth_ip):
        """Set ethernet interface as the default route with highest priority"""
        try:
            # Detect ethernet gateway
            gateway = self.detect_gateway_for_network(eth_ip)
            if not gateway:
                # Try common patterns
                ip_parts = eth_ip.split('.')
                gateway = '.'.join(ip_parts[:3]) + '.1'
            
            logger.info(f"🛣️ Setting {eth_iface} as default route via gateway {gateway}")
            
            # Remove any existing default routes
            self.run_command(["ip", "route", "del", "default"], log_output=False)
            time.sleep(1)
            
            # Add ethernet as default route with high priority (metric 100)
            result = self.run_command([
                "ip", "route", "add", "default", "via", gateway, 
                "dev", eth_iface, "metric", "100"
            ])
            
            if result and result.returncode == 0:
                logger.info(f"✅ Ethernet default route set: {eth_iface} via {gateway}")
                
                # Add WiFi route with lower priority if it exists
                wifi_ip = self.get_interface_ip('wlan0')
                if wifi_ip:
                    wifi_gateway = self.detect_gateway_for_network(wifi_ip)
                    if wifi_gateway:
                        self.run_command([
                            "ip", "route", "add", "default", "via", wifi_gateway,
                            "dev", "wlan0", "metric", "200"
                        ], log_output=False)
                        logger.info(f"📶 WiFi backup route added: wlan0 via {wifi_gateway} (lower priority)")
                
                return True
            else:
                logger.warning(f"⚠️ Failed to set ethernet default route")
                return False
                
        except Exception as e:
            logger.error(f"Failed to set ethernet default route: {e}")
            return False
    
    def handle_wifi_fallback(self, wifi_ip):
        """Handle WiFi fallback - only when ethernet is not active"""
        
        logger.info(f"📶 WIFI FALLBACK: Processing WiFi connection (IP: {wifi_ip})")
        
        # If ethernet is active, WiFi is secondary - don't change anything major
        if self.active_interface == 'ethernet':
            logger.info(f"🔌 Ethernet is active interface - WiFi serves as backup only")
            if wifi_ip:
                logger.info(f"📶 WiFi backup available: {wifi_ip}")
            else:
                logger.info(f"📶 WiFi connected but no IP (ethernet primary)")
            return
        
        # No ethernet active - WiFi becomes primary
        if wifi_ip:
            logger.info(f"📶 WiFi becomes primary interface: {wifi_ip}")
            self.active_interface = 'wifi'
            self.shared_ip = wifi_ip
            
            # Set WiFi as default route
            wifi_gateway = self.detect_gateway_for_network(wifi_ip)
            if wifi_gateway:
                # Clear existing default routes
                self.run_command(["ip", "route", "del", "default"], log_output=False)
                time.sleep(1)
                
                # Add WiFi as default route
                result = self.run_command([
                    "ip", "route", "add", "default", "via", wifi_gateway, "dev", "wlan0"
                ])
                if result and result.returncode == 0:
                    logger.info(f"✅ WiFi default route set via {wifi_gateway}")
            
            self.save_ip_state()
            return
        
        # WiFi connected but no IP - try to get one
        logger.info("📶 WiFi connected but no IP - requesting DHCP...")
        if self.get_dhcp_ip_for_interface('wlan0'):
            time.sleep(2)
            new_wifi_ip = self.get_interface_ip('wlan0')
            if new_wifi_ip:
                logger.info(f"✅ WiFi got IP: {new_wifi_ip}")
                self.active_interface = 'wifi'
                self.shared_ip = new_wifi_ip
                self.save_ip_state()
                return
        
        logger.warning("⚠️ WiFi connected but failed to get IP")
    
    def handle_no_network_connection(self):
        """Handle case where no network connection is available"""
        # Check if Ethernet might be available but without IP
        ethernet_info = self.detect_ethernet_connection()
        
        if ethernet_info and ethernet_info.get('connected') and not ethernet_info.get('ip'):
            # Ethernet connected but no IP - try to get shared IP or any IP
            request_ip = self.shared_ip if self.shared_ip else None
            logger.info(f"🔌 Ethernet connected but no IP - attempting DHCP (requesting: {request_ip})...")
            if self.get_dhcp_ip_for_interface(ethernet_info['interface'], request_ip):
                new_eth_ip = self.get_interface_ip(ethernet_info['interface'])
                if new_eth_ip:
                    if not self.shared_ip:
                        # First IP becomes our shared IP
                        self.shared_ip = new_eth_ip
                    self.active_interface = 'ethernet'
                    logger.info(f"🎯 Ethernet IP acquired: {new_eth_ip}")
                    self.save_ip_state()
                    return
        
        if self.shared_ip:
            logger.info(f"⚠️ No active network connection, but have reserved IP: {self.shared_ip}")
            # Keep the reserved IP for when network becomes available
        else:
            logger.info("❌ No network connection and no reserved IP")
            
        # Check if we should start hotspot mode
        if self.current_mode != 'hotspot':
            logger.info("🏗️ Starting hotspot mode due to no network connectivity")
            self.restart_hotspot()
    
    def transfer_ip_to_ethernet(self, eth_iface, target_ip, retries=3):
        """Transfer consistent IP to ethernet with conflict resolution"""
        logger.info(f"🔄 Transferring consistent IP {target_ip} to ethernet {eth_iface}")
        
        for attempt in range(retries):
            try:
                # Step 1: Ensure ethernet interface is ready
                self.run_command(["ip", "link", "set", eth_iface, "up"], log_output=False)
                time.sleep(1)
                
                # Step 2: Try DHCP first (requesting our consistent IP)
                logger.info(f"🌎 Attempt {attempt + 1}: Requesting {target_ip} via DHCP on ethernet")
                if self.get_dhcp_ip_for_interface(eth_iface, target_ip):
                    actual_ip = self.get_interface_ip(eth_iface)
                    if actual_ip == target_ip:
                        # Success! Remove ALL IPs from WiFi to avoid conflicts
                        current_wifi_ip = self.get_interface_ip('wlan0')
                        if current_wifi_ip:
                            logger.info(f"🔄 Removing all IPs from WiFi (ethernet now has {target_ip})")
                            self.run_command(["ip", "addr", "flush", "dev", "wlan0"], log_output=False)
                            time.sleep(1)
                        
                        self.active_interface = 'ethernet'
                        logger.info(f"✅ Ethernet successfully got consistent IP {target_ip} via DHCP")
                        return True
                    elif actual_ip:
                        logger.info(f"🎯 Ethernet got {actual_ip} (not {target_ip}), but ethernet is now active")
                        self.active_interface = 'ethernet'
                        # Keep shared_ip as the consistent IP for future WiFi connections
                        return True
                
                # Step 3: If DHCP didn't work, try static (more aggressive)
                logger.info(f"🔄 DHCP attempt {attempt + 1} failed, trying static assignment")
                
                # Clear ALL IPs from WiFi to avoid any conflicts
                current_wifi_ip = self.get_interface_ip('wlan0')
                if current_wifi_ip:
                    logger.info(f"🧩 Clearing all IPs from WiFi before ethernet static assignment")
                    self.run_command(["ip", "addr", "flush", "dev", "wlan0"], log_output=False)
                    time.sleep(2)  # Allow network stack to clear
                
                # Now try static assignment on ethernet
                if self.set_interface_ip(eth_iface, f"{target_ip}/24"):
                    self.active_interface = 'ethernet'
                    logger.info(f"✅ Ethernet got consistent IP {target_ip} via static assignment")
                    return True
                else:
                    logger.warning(f"❌ Static assignment failed (attempt {attempt + 1})")
                    time.sleep(3)  # Wait longer between attempts
                    
            except Exception as e:
                logger.error(f"Transfer attempt {attempt + 1} failed: {e}")
                time.sleep(3)
        
        # All attempts failed - let ethernet get any IP but keep it as active
        logger.warning(f"❌ Could not assign {target_ip} to ethernet - getting any available IP")
        if self.get_dhcp_ip_for_interface(eth_iface):
            eth_ip = self.get_interface_ip(eth_iface)
            if eth_ip:
                logger.info(f"🎯 Ethernet fallback IP: {eth_ip} (ethernet priority maintained)")
                self.active_interface = 'ethernet'
                # Keep shared_ip unchanged so WiFi gets consistent IP when ethernet disconnects
                return True
        
        logger.error(f"❌ Failed to get any IP for ethernet")
        return False
    
    def detect_gateway_for_network(self, ip):
        """Detect appropriate gateway for given IP"""
        try:
            # Common gateway patterns
            ip_parts = ip.split('.')
            if len(ip_parts) == 4:
                # Try common gateway: x.x.x.1
                gateway = '.'.join(ip_parts[:3]) + '.1'
                # Test if gateway responds
                ping_result = self.run_command(["ping", "-c", "1", "-W", "2", gateway], log_output=False)
                if ping_result and ping_result.returncode == 0:
                    return gateway
        except Exception as e:
            logger.debug(f"Gateway detection failed: {e}")
        return None
    
    def get_dhcp_ip_for_interface(self, interface, requested_ip=None):
        """Get DHCP IP for specific interface, always requesting saved IP if available"""
        try:
            # Kill existing DHCP clients for this interface
            self.run_command(["pkill", "-f", f"dhcp.*{interface}"], log_output=False)
            time.sleep(1)
            
            # Always try to get the same IP if we have one saved
            target_ip = requested_ip or self.shared_ip
            if target_ip:
                logger.info(f"🌎 Requesting consistent IP {target_ip} for {interface}")
            
            # Try dhcpcd first (preferred for IP requests)
            dhcpcd_paths = ["/sbin/dhcpcd", "/usr/sbin/dhcpcd", "/bin/dhcpcd"]
            for dhcpcd_path in dhcpcd_paths:
                if os.path.exists(dhcpcd_path):
                    logger.info(f"🌐 Using dhcpcd for {interface}")
                    cmd = [dhcpcd_path, "-4", "-t", "15"]
                    
                    # Request specific IP if we have one
                    if target_ip:
                        cmd.extend(["-r", target_ip])
                    
                    cmd.append(interface)
                    
                    result = self.run_command(cmd, timeout=20)
                    if result and result.returncode == 0:
                        time.sleep(3)  # Allow DHCP to complete
                        actual_ip = self.get_interface_ip(interface)
                        if actual_ip:
                            logger.info(f"✅ {interface} got IP via dhcpcd: {actual_ip}")
                            return True
                    break
            
            # Fallback to dhclient
            dhclient_paths = ["/sbin/dhclient", "/usr/sbin/dhclient"]
            for dhclient_path in dhclient_paths:
                if os.path.exists(dhclient_path):
                    logger.info(f"🌐 Fallback to dhclient for {interface}")
                    cmd = [dhclient_path, "-4", "-v", interface]
                    
                    result = self.run_command(cmd, timeout=20)
                    if result and result.returncode == 0:
                        time.sleep(3)
                        actual_ip = self.get_interface_ip(interface)
                        if actual_ip:
                            logger.info(f"✅ {interface} got IP via dhclient: {actual_ip}")
                            return True
                    break
                    
        except Exception as e:
            logger.error(f"DHCP failed for {interface}: {e}")
        
        return False
    
    def start_ethernet_monitoring(self):
        """Start background monitoring for ethernet connection changes with IP priority management"""
        if self.ethernet_monitoring_started:
            logger.debug("🔍 Ethernet monitoring already started")
            return
            
        def monitor_ethernet():
            last_ethernet_state = None
            last_wifi_state = None
            
            while True:
                try:
                    # Check ethernet and WiFi states every 3 seconds for faster response
                    ethernet_info = self.detect_ethernet_connection()
                    current_ethernet_state = ethernet_info is not None and ethernet_info.get('connected', False)
                    
                    # Check WiFi state more comprehensively
                    wifi_ip = self.get_interface_ip('wlan0')
                    wpa_status = self.run_command(["wpa_cli", "-i", "wlan0", "status"], log_output=False)
                    wifi_connected = (wpa_status and "wpa_state=COMPLETED" in wpa_status.stdout) if wpa_status else False
                    current_wifi_state = wifi_connected  # WiFi association, not IP-dependent
                    
                    # Log state changes with detailed info
                    ethernet_changed = current_ethernet_state != last_ethernet_state
                    wifi_changed = current_wifi_state != last_wifi_state
                    
                    # Debug logging every 30 seconds even if no changes
                    if not hasattr(self, 'last_debug_log'):
                        self.last_debug_log = 0
                    if time.time() - self.last_debug_log > 30:
                        logger.debug(f"🔍 Network Status: Ethernet={current_ethernet_state} ({ethernet_info.get('ip') if ethernet_info else 'None'}), WiFi={current_wifi_state} (IP={wifi_ip})")
                        self.last_debug_log = time.time()
                    
                    if ethernet_changed or wifi_changed:
                        if ethernet_changed:
                            if current_ethernet_state:
                                logger.info(f"🔌 ETHERNET CONNECTED - Triggering IP priority management... (IP: {ethernet_info.get('ip')})")
                            else:
                                logger.info("🔌 ETHERNET DISCONNECTED - Switching to WiFi...")
                                # Force WiFi to get IP when Ethernet disconnects (simple DHCP)
                                if current_wifi_state and not wifi_ip:
                                    logger.info("🔌 Getting DHCP IP for WiFi after Ethernet disconnect")
                                    try:
                                        if self.get_dhcp_ip_for_interface('wlan0'):
                                            new_wifi_ip = self.get_interface_ip('wlan0')
                                            logger.info(f"✅ WiFi IP acquired: {new_wifi_ip}")
                                    except Exception as dhcp_e:
                                        logger.error(f"❌ Failed to get WiFi IP: {dhcp_e}")
                        
                        if wifi_changed:
                            if current_wifi_state:
                                logger.info(f"📶 WiFi CONNECTED - Updating IP priority... (IP: {wifi_ip})")
                            else:
                                logger.info("📶 WiFi DISCONNECTED")
                        
                        # Trigger IP priority management on any network change
                        try:
                            self.manage_enhanced_network_priority()
                            logger.info(f"🎯 IP Priority Updated: Active={self.active_interface}, IP={self.shared_ip}")
                            
                            # Special case: If ethernet connected while in hotspot mode, prioritize ethernet
                            if ethernet_changed and current_ethernet_state and self.current_mode == "hotspot":
                                logger.info("🔌 Ethernet detected during hotspot mode - switching to ethernet priority")
                                self.current_mode = "client"  # Switch out of hotspot mode
                            
                            # Extra check: if Ethernet just disconnected and WiFi is connected but has no IP
                            if ethernet_changed and not current_ethernet_state and current_wifi_state:
                                wifi_check_ip = self.get_interface_ip('wlan0')
                                if not wifi_check_ip:
                                    logger.warning("⚠️ WiFi connected but no IP after Ethernet disconnect - getting DHCP")
                                    if self.get_dhcp_ip_for_interface('wlan0'):
                                        final_ip = self.get_interface_ip('wlan0')
                                        logger.info(f"✅ WiFi DHCP successful: {final_ip}")
                                        self.active_interface = 'wifi'
                                        self.save_ip_state()
                        except Exception as e:
                            logger.error(f"Failed to update IP priority: {e}")
                        
                        last_ethernet_state = current_ethernet_state
                        last_wifi_state = current_wifi_state
                    
                    time.sleep(3)  # Check every 3 seconds for faster response
                    
                except Exception as e:
                    logger.debug(f"Ethernet monitoring error: {e}")
                    time.sleep(3)
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitor_ethernet, daemon=True)
        monitor_thread.start()
        self.ethernet_monitoring_started = True
        logger.info("🔍 Started continuous network monitoring with IP priority management")
        
        # Also start button monitor health check
        self.start_button_monitor_health_check()
    
    def start_button_monitor_health_check(self):
        """Start health check for button monitor process"""
        def check_button_monitor():
            while True:
                try:
                    time.sleep(30)  # Check every 30 seconds
                    
                    # Check if button monitor is running
                    result = self.run_command(["pgrep", "-f", "button_monitor.py"], log_output=False)
                    if not result or result.returncode != 0:
                        logger.warning("⚠️ Button monitor not running - process may have died")
                        logger.info("🔄 Button monitor status check failed")
                    else:
                        logger.debug("🔘 Button monitor health check: OK")
                        
                except Exception as e:
                    logger.debug(f"Button monitor health check error: {e}")
        
        # Start health check in background thread
        health_thread = threading.Thread(target=check_button_monitor, daemon=True)
        health_thread.start()
        logger.info("🔘 Started button monitor health check")

    def restart_hotspot(self):
        """Restart hotspot mode with enhanced reliability"""
        logger.info("🏗️ Restarting hotspot mode...")

        try:
            # Stop all services
            self.stop_all_network_services()
            time.sleep(5)  # Give more time for services to stop

            # Reset wlan0 interface
            logger.info("🔄 Resetting wlan0 interface for hotspot...")
            self.run_command(["ip", "link", "set", "wlan0", "down"])
            time.sleep(2)
            self.run_command(["ip", "addr", "flush", "dev", "wlan0"])
            time.sleep(1)
            self.run_command(["ip", "route", "flush", "dev",
                             "wlan0"], log_output=False)
            time.sleep(1)
            self.run_command(["ip", "link", "set", "wlan0", "up"])
            time.sleep(3)  # Give interface time to come up
            self.run_command(
                ["ip", "addr", "add", "192.168.4.1/24", "dev", "wlan0"])
            time.sleep(2)

            # Verify interface is configured
            result = self.run_command(
                ["ip", "addr", "show", "wlan0"], log_output=False)
            if result and "192.168.4.1" in result.stdout:
                logger.info("✅ wlan0 interface configured for hotspot")
            else:
                logger.error("❌ Failed to configure wlan0 interface")
                return False

            # Create enhanced hostapd config
            hostapd_config = f"""# WiFi Onboarding Hotspot Configuration
interface=wlan0
driver=nl80211
ssid={self.hotspot_ssid}
hw_mode=g
channel=6
auth_algs=1
wpa=0

# Improve compatibility and performance
ieee80211n=1
wmm_enabled=1

# Set country code for regulatory compliance
country_code=US

# Increase beacon interval for better mobile detection
beacon_int=100

# Enable HT capabilities for better performance
ht_capab=[HT40][SHORT-GI-20][DSSS_CCK-40]

# Improve AP discovery
ignore_broadcast_ssid=0
max_num_sta=10
"""

            with open('/tmp/hostapd.conf', 'w') as f:
                f.write(hostapd_config)

            # Start hostapd
            logger.info("📡 Starting hostapd...")
            hostapd_proc = subprocess.Popen(["hostapd", "/tmp/hostapd.conf"])
            time.sleep(5)  # Give hostapd time to start

            # Check if hostapd is running
            if hostapd_proc.poll() is None:  # Process is still running
                logger.info("✅ hostapd started successfully")
                
                # Clear reset flag immediately when hostapd is ready - don't wait for dnsmasq
                try:
                    if os.path.exists("/tmp/wifi_reset"):
                        os.remove("/tmp/wifi_reset")
                        logger.info("🚩 Reset flag cleared - WiFi connections now allowed")
                except Exception as e:
                    logger.debug(f"Failed to clear reset flag: {e}")
                    
            else:
                logger.error("❌ hostapd failed to start")
                return False

            # Start enhanced dnsmasq
            logger.info("🌐 Starting dnsmasq...")
            dnsmasq_proc = subprocess.Popen([
                "dnsmasq",
                "--interface=wlan0",
                "--dhcp-range=192.168.4.10,192.168.4.50,12h",
                "--dhcp-option=3,192.168.4.1",  # Gateway
                "--dhcp-option=6,192.168.4.1",  # DNS server
                "--server=8.8.8.8",
                "--server=8.8.4.4",
                "--address=/#/192.168.4.1",  # Catch-all DNS
                # Specific captive portal domains
                "--address=/connectivitycheck.gstatic.com/192.168.4.1",
                "--address=/clients3.google.com/192.168.4.1",
                "--address=/play.googleapis.com/192.168.4.1",
                "--address=/captive.apple.com/192.168.4.1",
                "--address=/www.apple.com/192.168.4.1",
                "--address=/www.msftncsi.com/192.168.4.1",
                "--address=/msftconnecttest.com/192.168.4.1",
                "--address=/detectportal.firefox.com/192.168.4.1",
                "--address=/connectivitycheck.android.com/192.168.4.1",
                "--address=/google.com/192.168.4.1",
                "--address=/www.google.com/192.168.4.1",
                "--no-resolv",
                "--no-hosts",
                "--log-queries",  # For debugging
                "--log-dhcp"
            ])
            time.sleep(3)

            # Check if dnsmasq is running
            if dnsmasq_proc.poll() is None:  # Process is still running
                logger.info("✅ dnsmasq started successfully")
            else:
                logger.error("❌ dnsmasq failed to start")
                return False

            self.current_mode = "hotspot"
            logger.info("✅ Hotspot mode restarted successfully")
            logger.info(f"📱 Hotspot SSID: {self.hotspot_ssid}")
            logger.info("🌐 Access point ready at: http://192.168.4.1")

            return True

        except Exception as e:
            logger.error(f"Failed to restart hotspot: {e}")
            return False

    def save_config(self, ssid, password):
        """Save WiFi configuration including static IP settings"""
        try:
            config = {
                "ssid": ssid,
                "password": password,
                "configured": True,
                "timestamp": time.time(),
                "use_static_ip": self.use_static_ip,
                "static_ip": self.static_ip if self.use_static_ip else None,
                "static_gateway": self.static_gateway if self.use_static_ip else None,
                "static_dns": self.static_dns if self.use_static_ip else None
            }
            os.makedirs("/data", exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)

            if self.use_static_ip:
                logger.info(
                    f"💾 Configuration saved: {ssid} with static IP {self.static_ip}")
            else:
                logger.info(f"💾 Configuration saved: {ssid} with DHCP")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def load_config(self):
        """Load WiFi configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        return None

    def reset_wifi(self):
        """Reset WiFi configuration and return to hotspot"""
        logger.info("🔄 Resetting WiFi configuration...")

        # Stop enhanced network monitoring to prevent interference
        self.ethernet_monitoring_started = False
        time.sleep(2)  # Give monitoring threads time to notice
        
        # Stop all services FIRST
        self.stop_all_network_services()
        time.sleep(3)  # Give services time to stop

        # FORCE reset wlan0 interface before hotspot
        logger.info("🔧 Force resetting wlan0 interface...")
        self.run_command(["ip", "link", "set", "wlan0", "down"], log_output=False)
        time.sleep(2)
        
        # Disconnect from any wireless networks
        self.run_command(["iw", "dev", "wlan0", "disconnect"], log_output=False)
        time.sleep(1)
        
        # Flush all addresses and routes
        self.run_command(["ip", "addr", "flush", "dev", "wlan0"], log_output=False)
        self.run_command(["ip", "route", "flush", "dev", "wlan0"], log_output=False)
        time.sleep(2)
        
        # Bring interface back up
        self.run_command(["ip", "link", "set", "wlan0", "up"], log_output=False)
        time.sleep(3)  # Give interface time to stabilize

        # Remove saved config with verification
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
                logger.info("🗑️ Removed saved configuration")
                # Verify it's actually gone  
                if os.path.exists(self.config_file):
                    logger.error("❌ Config file still exists after removal!")
                else:
                    logger.info("✅ Config file successfully removed")
        except Exception as e:
            logger.error(f"Failed to remove config: {e}")

        # Remove ALL temporary files that could cause auto-reconnect
        temp_files = [
            "/tmp/wpa_supplicant.conf", 
            "/tmp/wifi_reset",
            "/tmp/wifi_state.json",
            "/tmp/ip_state.json",
            "/tmp/hostapd.conf"
        ]
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"🗑️ Removed {temp_file}")
            except Exception as e:
                logger.debug(f"Failed to remove {temp_file}: {e}")

        # Create a reset flag to prevent auto-reconnect
        try:
            with open("/tmp/wifi_reset", "w") as f:
                f.write("reset_in_progress")
            logger.info("🚩 Created reset flag to prevent auto-reconnect")
        except Exception as e:
            logger.warning(f"Failed to create reset flag: {e}")

        # Restart hotspot with clean interface
        self.restart_hotspot()
        
        # Reset network state after WiFi reset
        self.shared_ip = None
        self.active_interface = None
        self.reserved_ip = None
        self.current_mode = "hotspot"
        
        # Restart enhanced network monitoring for ethernet detection
        if self.dual_network:
            logger.info("🚀 Restarting enhanced network monitoring after reset...")
            try:
                # Reset monitoring state
                self.ethernet_monitoring_started = False
                # Start monitoring for ethernet detection
                self.start_ethernet_monitoring()
            except Exception as e:
                logger.error(f"Failed to restart ethernet monitoring: {e}")
        
        logger.info("🔄 WiFi reset completed - system ready for reconfiguration")

    def get_current_ip(self):
        """Get current wlan0 IP address"""
        try:
            result = self.run_command(
                ["ip", "addr", "show", "wlan0"], log_output=False)
            if result and result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if "inet " in line:
                        return line.strip().split()[1]
        except Exception as e:
            logger.debug(f"Failed to get IP: {e}")
        return "No IP"

    def get_network_status(self):
        """Get current network status"""
        return {
            "mode": self.current_mode,
            "ip": self.get_current_ip(),
            "config": self.load_config()
        }


# Global controller
wifi_controller = WorkingWiFiController()

# HTML Template with status display
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 500px; 
            margin: 0 auto; 
            padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container { 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        h1 { 
            color: #333; 
            text-align: center; 
            margin-bottom: 30px; 
            font-size: 28px;
        }
        .status-box {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #28a745;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }
        input { 
            width: 100%; 
            padding: 15px; 
            border: 2px solid #e0e0e0; 
            border-radius: 8px; 
            box-sizing: border-box;
            font-size: 16px;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            padding: 15px; 
            width: 100%; 
            border: none; 
            border-radius: 8px; 
            font-size: 16px; 
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
        }
        .status { 
            margin-top: 20px; 
            padding: 15px; 
            border-radius: 8px; 
            text-align: center;
            font-weight: 600;
        }
        .success { 
            background: #d4edda; 
            color: #155724; 
        }
        .error { 
            background: #f8d7da; 
            color: #721c24; 
        }
        .info-box {
            margin-top: 30px; 
            padding: 20px; 
            background: #e3f2fd;
            border-radius: 8px; 
            font-size: 14px;
            line-height: 1.6;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 10px;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 WiFi Setup</h1>
        
        <div class="status-box">
            <strong>📊 Current Status:</strong><br>
            Mode: <span style="color: #28a745;">{{ mode }}</span><br>
            wlan0 IP: <span style="color: #007bff;">{{ current_ip }}</span>
        </div>
        
        <form method="POST" id="wifiForm">
            <div class="form-group">
                <label for="ssid">WiFi Network Name (SSID):</label>
                <input type="text" id="ssid" name="ssid" placeholder="Enter WiFi network name" required>
            </div>
            
            <div class="form-group">
                <label for="password">WiFi Password:</label>
                <input type="password" id="password" name="password" placeholder="Enter password (leave blank for open networks)">
            </div>
            
            <div class="form-group">
                <label>
                    <input type="checkbox" id="useStaticIp" name="use_static_ip" style="margin-right: 8px;">
                    Use Static IP Address (recommended for consistent access)
                </label>
            </div>
            
            <div id="staticIpFields" style="display: none;">
                <div class="form-group">
                    <label for="static_ip">Static IP Address:</label>
                    <input type="text" id="static_ip" name="static_ip" placeholder="192.168.1.100" value="192.168.6.161">
                </div>
                
                <div class="form-group">
                    <label for="static_gateway">Gateway (Router IP):</label>
                    <input type="text" id="static_gateway" name="static_gateway" placeholder="192.168.1.1" value="192.168.6.1">
                </div>
                
                <div class="form-group">
                    <label for="static_dns">DNS Server:</label>
                    <input type="text" id="static_dns" name="static_dns" placeholder="8.8.8.8" value="8.8.8.8">
                </div>
            </div>
            
            <button type="submit" id="connectBtn">🔗 Connect to WiFi</button>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Connecting to WiFi network...<br>This may take up to 60 seconds.</p>
            </div>
        </form>
        
        {{ status_message }}
        
        <div class="info-box">
            <strong>🎯 How it works:</strong><br>
            • Enter your home WiFi credentials above<br>
            • Device stops hotspot and connects to your WiFi<br>
            • wlan0 gets real IP from your router via DHCP<br>
            • You can then disconnect ethernet cable<br>
            • Device works purely on WiFi!<br><br>
            
            <strong>🔄 Reset WiFi:</strong><br>
            Hold the physical button for 5 seconds to reset and return to hotspot mode.
        </div>
    </div>
    
    <script>
        // Show/hide static IP fields based on checkbox
        document.getElementById('useStaticIp').addEventListener('change', function() {
            const staticFields = document.getElementById('staticIpFields');
            if (this.checked) {
                staticFields.style.display = 'block';
            } else {
                staticFields.style.display = 'none';
            }
        });
        
        document.getElementById('wifiForm').addEventListener('submit', function() {
            document.getElementById('connectBtn').style.display = 'none';
            document.getElementById('loading').style.display = 'block';
        });
    </script>
</body>
</html>
"""


@app.route('/', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        # Check if we're in reset mode
        if os.path.exists("/tmp/wifi_reset"):
            logger.warning("🚩 WiFi connection blocked - system in reset mode")
            status_msg = '<div class="status error">🔄 System is resetting - please wait and refresh page</div>'
            return render_template_string(HTML_TEMPLATE,
                                          status_message=status_msg,
                                          mode="hotspot",
                                          current_ip="192.168.4.1")
        
        ssid = request.form.get('ssid', '').strip()
        password = request.form.get('password', '').strip()
        use_static_ip = request.form.get('use_static_ip') == 'on'

        if not ssid:
            status_msg = '<div class="status error">❌ Please enter a network name</div>'
            return render_template_string(HTML_TEMPLATE,
                                          status_message=status_msg,
                                          mode=wifi_controller.current_mode,
                                          current_ip=wifi_controller.get_current_ip())

        # Configure static IP settings if requested
        if use_static_ip:
            static_ip = request.form.get('static_ip', '').strip()
            static_gateway = request.form.get('static_gateway', '').strip()
            static_dns = request.form.get('static_dns', '8.8.8.8').strip()

            if not static_ip or not static_gateway:
                status_msg = '<div class="status error">❌ Please enter both static IP and gateway</div>'
                return render_template_string(HTML_TEMPLATE,
                                              status_message=status_msg,
                                              mode=wifi_controller.current_mode,
                                              current_ip=wifi_controller.get_current_ip())

            # Apply static IP configuration
            wifi_controller.use_static_ip = True
            wifi_controller.static_ip = static_ip
            wifi_controller.static_gateway = static_gateway
            wifi_controller.static_dns = static_dns

            logger.info(f"WiFi setup with static IP: {ssid} -> {static_ip}")
        else:
            wifi_controller.use_static_ip = False
            logger.info(f"WiFi setup with DHCP: {ssid}")

        # Connect to WiFi using the complete connection method
        success = wifi_controller.connect_to_wifi(ssid, password)

        if success:
            current_ip = wifi_controller.get_current_ip()
            return render_template_string("""
            <div class="container">
                <h1>🎉 WiFi Connected!</h1>
                <div class="status success">
                    ✅ Successfully connected to <strong>{{ ssid }}</strong>!<br><br>
                    
                    🌐 <strong>wlan0 IP: {{ current_ip }}</strong><br>
                    📡 Device is connected to your WiFi network<br>
                    🔌 You can now disconnect the ethernet cable<br>
                    🔄 Device will auto-reconnect on reboot<br><br>
                    
                    <strong>Your Home Assistant is now running on WiFi!</strong>
                </div>
                
                <div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 8px; font-size: 14px;">
                    <strong>💡 Next Steps:</strong><br>
                    • Disconnect from "WiFi-Setup" hotspot<br>
                    • Access Home Assistant via your main WiFi network<br>
                    • Ethernet cable can be removed safely<br>
                    • Device will reconnect automatically after reboot
                </div>
            </div>
            """, ssid=ssid, current_ip=current_ip)
        else:
            status_msg = f'<div class="status error">❌ Failed to connect to "{ssid}"<br>📡 Returned to hotspot mode - please try again<br>💡 Check password and network availability</div>'
            return render_template_string(HTML_TEMPLATE,
                                          status_message=status_msg,
                                          mode=wifi_controller.current_mode,
                                          current_ip=wifi_controller.get_current_ip())

    # GET request - show setup form
    return render_template_string(HTML_TEMPLATE,
                                  status_message="",
                                  mode=wifi_controller.current_mode,
                                  current_ip=wifi_controller.get_current_ip())


@app.route('/status')
def status():
    """Enhanced API endpoint for detailed status"""
    try:
        base_status = wifi_controller.get_network_status()

        # Add additional system information
        additional_info = {
            "timestamp": time.time(),
            "uptime": time.time() - (time.time() - 300),  # Rough uptime
            "hotspot_ssid": wifi_controller.hotspot_ssid,
            "interface_state": "unknown",
            # Enhanced network management info
            "shared_ip": wifi_controller.shared_ip,
            "active_interface": wifi_controller.active_interface,
            "reserved_ip": wifi_controller.reserved_ip,
            "ethernet_monitoring": wifi_controller.ethernet_monitoring_started,
            "priority_status": f"ACTIVE: {wifi_controller.active_interface or 'none'}"
        }

        # Get detailed interface information
        try:
            result = wifi_controller.run_command(
                ["ip", "addr", "show", "wlan0"], log_output=False)
            if result and result.returncode == 0:
                if "UP" in result.stdout:
                    additional_info["interface_state"] = "up"
                else:
                    additional_info["interface_state"] = "down"

                # Extract all IP addresses
                ips = []
                for line in result.stdout.split('\n'):
                    if "inet " in line:
                        ip_info = line.strip().split()[1] if len(
                            line.strip().split()) > 1 else "unknown"
                        ips.append(ip_info)
                additional_info["all_ips"] = ips
        except:
            pass

        # Check if services are running
        service_status = {}
        for service in ["hostapd", "dnsmasq", "wpa_supplicant"]:
            try:
                result = wifi_controller.run_command(
                    ["pgrep", "-f", service], log_output=False)
                service_status[service] = "running" if result and result.returncode == 0 else "stopped"
            except:
                service_status[service] = "unknown"

        additional_info["services"] = service_status
        
        # Add ethernet connection information
        try:
            ethernet_info = wifi_controller.detect_ethernet_connection()
            additional_info["ethernet_info"] = ethernet_info
            if ethernet_info:
                additional_info["ethernet_connected"] = ethernet_info.get('connected', False)
                additional_info["ethernet_ip"] = ethernet_info.get('ip')
                additional_info["ethernet_interface"] = ethernet_info.get('interface')
            else:
                additional_info["ethernet_connected"] = False
                additional_info["ethernet_ip"] = None
                additional_info["ethernet_interface"] = None
        except:
            additional_info["ethernet_info"] = None
            additional_info["ethernet_connected"] = False

        # Merge all information
        base_status.update(additional_info)

        return jsonify(base_status)

    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route('/clear_config', methods=['POST'])
def clear_config():
    """API endpoint to clear saved configuration"""
    try:
        if os.path.exists(wifi_controller.config_file):
            os.remove(wifi_controller.config_file)
            logger.info("🗑️ Saved configuration cleared")
        wifi_controller.restart_hotspot()
        return jsonify({"success": True, "message": "Configuration cleared and hotspot restarted"})
    except Exception as e:
        logger.error(f"Failed to clear config: {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route('/debug')
def debug():
    """Enhanced debug endpoint to show current status and boot issues"""
    try:
        # Get current config
        config = wifi_controller.load_config()

        # Get wlan0 status
        ip_result = wifi_controller.run_command(
            ["ip", "addr", "show", "wlan0"], log_output=False)
        wlan0_info = ip_result.stdout if ip_result and ip_result.returncode == 0 else "Error getting wlan0 info"

        # Get routing table
        route_result = wifi_controller.run_command(
            ["ip", "route"], log_output=False)
        route_info = route_result.stdout if route_result and route_result.returncode == 0 else "Error getting route info"

        # Get wpa_supplicant status if running
        wpa_status = ""
        wpa_result = wifi_controller.run_command(
            ["wpa_cli", "-i", "wlan0", "status"], log_output=False)
        if wpa_result and wpa_result.returncode == 0:
            wpa_status = wpa_result.stdout

        # Get scan results
        scan_status = ""
        scan_result = wifi_controller.run_command(
            ["wpa_cli", "-i", "wlan0", "scan_results"], log_output=False)
        if scan_result and scan_result.returncode == 0:
            scan_status = scan_result.stdout

        # Check running processes
        processes = {}
        for service in ["hostapd", "dnsmasq", "wpa_supplicant", "dhcpcd"]:
            proc_result = wifi_controller.run_command(
                ["pgrep", "-f", service], log_output=False)
            processes[service] = "running" if proc_result and proc_result.returncode == 0 else "stopped"

        # Check files
        file_status = {
            "config_file": os.path.exists(wifi_controller.config_file),
            "wpa_conf": os.path.exists("/tmp/wpa_supplicant.conf"),
            "hostapd_conf": os.path.exists("/tmp/hostapd.conf"),
            "reset_flag": os.path.exists("/tmp/wifi_reset")
        }

        # Get system uptime (rough)
        uptime_result = wifi_controller.run_command(
            ["uptime"], log_output=False)
        uptime_info = uptime_result.stdout if uptime_result and uptime_result.returncode == 0 else "Unknown"

        debug_info = {
            "timestamp": time.time(),
            "current_mode": wifi_controller.current_mode,
            "saved_config": config,
            "wlan0_info": wlan0_info,
            "route_info": route_info,
            "wpa_status": wpa_status,
            "scan_results": scan_status,
            "processes": processes,
            "files": file_status,
            "uptime": uptime_info,
            "hotspot_ssid": wifi_controller.hotspot_ssid,
            "config_file_path": wifi_controller.config_file
        }

        return jsonify(debug_info)

    except Exception as e:
        return jsonify({"error": str(e), "traceback": str(e)})


@app.route('/reset', methods=['GET', 'POST'])
def reset():
    """API endpoint for reset - supports both GET and POST for convenience"""
    try:
        logger.info("🔄 Manual reset requested via web interface")
        wifi_controller.reset_wifi()

        if request.method == 'GET':
            # Return HTML response for browser access
            return '''
            <html>
            <head><title>WiFi Reset</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>🔄 WiFi Reset Complete</h1>
            <p>The device has been reset and is returning to hotspot mode.</p>
            <p>Please wait 30 seconds, then connect to "WiFi-Setup" hotspot.</p>
            <p><a href="http://192.168.4.1">Click here to setup WiFi again</a></p>
            </body>
            </html>
            '''
        else:
            # Return JSON for API access
            return jsonify({"success": True, "message": "WiFi reset to hotspot mode"})
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        if request.method == 'GET':
            return f'<html><body><h1>Reset Failed</h1><p>Error: {str(e)}</p></body></html>'
        else:
            return jsonify({"success": False, "message": str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})


@app.route('/test_reset')
def test_reset():
    """Test endpoint to manually trigger reset (for debugging)"""
    try:
        logger.info("🧪 Manual reset test triggered via web interface")
        wifi_controller.reset_wifi()
        return jsonify({
            "success": True, 
            "message": "Manual reset completed",
            "current_mode": wifi_controller.current_mode,
            "active_interface": wifi_controller.active_interface
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/button_test')
def button_test():
    """Test endpoint to check button status"""
    try:
        # Check if button monitor is running
        result = os.system("pgrep -f button_monitor.py > /dev/null")
        button_running = result == 0

        # Get GPIO info
        # Check for button monitor process more thoroughly
        button_processes = []
        try:
            result = subprocess.run(["pgrep", "-f", "button_monitor"], capture_output=True, text=True)
            if result.returncode == 0:
                button_processes = result.stdout.strip().split('\n')
        except:
            pass
        
        gpio_info = {
            "button_monitor_running": button_running,
            "button_processes": button_processes,
            "button_process_count": len(button_processes) if button_processes[0] else 0,
            "gpio_pin": 11,
            "reset_count": wifi_controller.reset_count,
            "last_reset_time": wifi_controller.last_reset_time,
            "seconds_since_last_reset": time.time() - wifi_controller.last_reset_time if wifi_controller.last_reset_time > 0 else -1,
            "reset_flag_exists": os.path.exists("/tmp/wifi_reset"),
            "config_file_exists": os.path.exists(wifi_controller.config_file),
            "expected_files": {
                "/dev/gpiomem": os.path.exists("/dev/gpiomem"),
                "/dev/gpiochip0": os.path.exists("/dev/gpiochip0"),
                "/sys/class/gpio": os.path.exists("/sys/class/gpio")
            },
            "instructions": "Press button for 5+ seconds to trigger reset"
        }

        return jsonify(gpio_info)
    except Exception as e:
        return jsonify({"error": str(e)})

# Captive portal redirects


@app.route('/generate_204')
@app.route('/gen_204')
@app.route('/hotspot-detect.html')
@app.route('/connectivity-check.html')
def captive_portal():
    """Handle captive portal detection"""
    return '', 204


def initialize_on_startup():
    """Initialize system - check for saved WiFi or start hotspot"""
    logger.info("🚀 Initializing WiFi Onboarding System")

    # Check for reset flag first
    if os.path.exists("/tmp/wifi_reset"):
        logger.info("🔄 Reset flag detected - clearing configuration")
        try:
            os.remove("/tmp/wifi_reset")
            if os.path.exists(wifi_controller.config_file):
                os.remove(wifi_controller.config_file)
        except:
            pass

    # Check for saved WiFi configuration
    config = wifi_controller.load_config()
    if config and config.get('configured'):
        ssid = config['ssid']
        password = config.get('password', '')

        # Load static IP configuration if available
        if config.get('use_static_ip', False):
            wifi_controller.use_static_ip = True
            wifi_controller.static_ip = config.get(
                'static_ip', '192.168.1.100')
            wifi_controller.static_gateway = config.get(
                'static_gateway', '192.168.1.1')
            wifi_controller.static_dns = config.get('static_dns', '8.8.8.8')
            logger.info(
                f"🔄 Found saved WiFi configuration: {ssid} with static IP {wifi_controller.static_ip}")
        else:
            wifi_controller.use_static_ip = False
            logger.info(f"🔄 Found saved WiFi configuration: {ssid} with DHCP")

        # Give the system more time to initialize on boot
        logger.info("⏳ Waiting for system to fully initialize...")

        # Wait for network interfaces to be ready
        for wait_time in range(20):  # Wait up to 20 seconds
            try:
                # Check if wlan0 exists and is up
                result = subprocess.run(['ip', 'link', 'show', 'wlan0'],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'state UP' in result.stdout:
                    logger.info("✅ wlan0 interface is ready")
                    break
                elif result.returncode == 0:
                    logger.info(
                        f"🔍 wlan0 exists but not ready: {result.stdout.split('state ')[1].split(' ')[0] if 'state ' in result.stdout else 'unknown state'}")
                    # Try to bring it up
                    subprocess.run(['ip', 'link', 'set', 'wlan0', 'up'],
                                   capture_output=True, timeout=5)
            except Exception as e:
                logger.debug(f"Interface check failed: {e}")

            logger.info(
                f"⏳ Waiting for network interface... ({wait_time + 1}/20)")
            time.sleep(1)

        # Check for conflicting network services on boot
        logger.info("🔍 Checking for conflicting network services...")
        try:
            # Check for NetworkManager
            result = subprocess.run(['systemctl', 'is-active', 'NetworkManager'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and 'active' in result.stdout:
                logger.warning(
                    "⚠️ NetworkManager is active - may conflict with manual WiFi management")
                # Try to stop NetworkManager from managing wlan0
                subprocess.run(['nmcli', 'device', 'set', 'wlan0', 'managed', 'no'],
                               capture_output=True, timeout=5)
                logger.info("🔧 Set wlan0 to unmanaged by NetworkManager")
        except Exception as e:
            logger.debug(f"NetworkManager check failed: {e}")

        # Ensure no previous WiFi processes are running
        logger.info("🛑 Ensuring clean network state...")
        cleanup_commands = [
            ['pkill', '-f', 'wpa_supplicant'],
            ['pkill', '-f', 'dhcpcd'],
            ['pkill', '-f', 'udhcpc'],
            ['pkill', '-f', 'hostapd'],
            ['pkill', '-f', 'dnsmasq']
        ]

        for cmd in cleanup_commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
            except:
                pass

        time.sleep(2)  # Brief pause after cleanup

        # Additional boot delay for system stability
        logger.info("⏳ Additional boot delay for system stability...")
        time.sleep(3)

        # Try to connect to saved WiFi with retry logic
        logger.info("🔗 Attempting to connect to saved WiFi...")

        max_retries = 5  # Increased retries for boot
        for attempt in range(max_retries):
            logger.info(f"🔄 Connection attempt {attempt + 1}/{max_retries}")

            # Check interface status before attempting connection
            try:
                result = subprocess.run(['ip', 'addr', 'show', 'wlan0'],
                                        capture_output=True, text=True, timeout=5)
                logger.info(
                    f"🔍 wlan0 status before attempt: {result.stdout.split('inet ')[1].split(' ')[0] if 'inet ' in result.stdout else 'no IP'}")
            except:
                pass

            if wifi_controller.connect_to_wifi(ssid, password):
                logger.info("✅ Successfully connected to saved WiFi")

                # Verify the connection is actually working
                try:
                    result = subprocess.run(['ip', 'addr', 'show', 'wlan0'],
                                            capture_output=True, text=True, timeout=5)
                    if 'inet ' in result.stdout:
                        ip_addr = result.stdout.split('inet ')[1].split(' ')[0]
                        logger.info(f"🌐 Device is ready on WiFi: {ip_addr}")
                        
                        # Start enhanced network management with Ethernet priority
                        if wifi_controller.dual_network:
                            logger.info("🚀 Starting enhanced network management with Ethernet priority...")
                            wifi_controller.manage_enhanced_network_priority()
                            wifi_controller.start_ethernet_monitoring()
                        
                        return True
                    else:
                        logger.warning(
                            "⚠️ Connection succeeded but no IP assigned")
                except Exception as e:
                    logger.warning(f"⚠️ Could not verify IP assignment: {e}")
                    
                    # Still start enhanced network management since connection succeeded
                    if wifi_controller.dual_network:
                        logger.info("🚀 Starting enhanced network management (connection assumed successful)...")
                        wifi_controller.manage_enhanced_network_priority()
                        wifi_controller.start_ethernet_monitoring()
                    
                    return True  # Assume success if we can't verify

            else:
                logger.warning(
                    f"❌ WiFi connection attempt {attempt + 1} failed")
                if attempt < max_retries - 1:
                    logger.info("⏳ Waiting before retry...")
                    time.sleep(20)  # Longer wait between attempts on boot

        logger.warning("❌ All WiFi connection attempts failed")
        logger.info("🏗️ Starting hotspot mode for reconfiguration")

        # Start hotspot services since WiFi connection failed
        try:
            wifi_controller.restart_hotspot()
        except Exception as e:
            logger.error(f"Failed to start hotspot after WiFi failure: {e}")
    else:
        logger.info(
            "🏗️ No saved WiFi configuration found - starting hotspot mode")

        # Start hotspot services for initial configuration
        try:
            wifi_controller.restart_hotspot()
        except Exception as e:
            logger.error(f"Failed to start initial hotspot: {e}")

    # Set mode and log status
    wifi_controller.current_mode = "hotspot"
    logger.info("✅ Hotspot mode active - ready for configuration")
    logger.info(f"📱 Connect to: {wifi_controller.hotspot_ssid}")
    logger.info("🌐 Browse to: http://192.168.4.1")
    
    # Always start enhanced network management for ethernet detection
    if wifi_controller.dual_network:
        logger.info("🚀 Starting enhanced network management for ethernet detection...")
        try:
            wifi_controller.start_ethernet_monitoring()
        except Exception as e:
            logger.error(f"Failed to start ethernet monitoring: {e}")

    return True


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    wifi_controller.stop_all_network_services()
    sys.exit(0)


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    def handle_reset_signal(signum, frame):
        """Handle reset signal from button monitor with enhanced logging"""
        wifi_controller.reset_count += 1
        wifi_controller.last_reset_time = time.time()
        logger.info(f"🔄 Reset signal #{wifi_controller.reset_count} received from button monitor")
        logger.info(f"📊 Current state: mode={wifi_controller.current_mode}, active_interface={wifi_controller.active_interface}")
        try:
            wifi_controller.reset_wifi()
            logger.info(f"✅ WiFi reset #{wifi_controller.reset_count} completed successfully")
        except Exception as e:
            logger.error(f"❌ WiFi reset #{wifi_controller.reset_count} failed: {e}")
    
    signal.signal(signal.SIGUSR1, handle_reset_signal)

    # Create PID file for button monitor to find us
    try:
        with open("/tmp/onboarding.pid", "w") as f:
            f.write(str(os.getpid()))
        logger.info(f"📝 Created PID file: {os.getpid()}")
    except Exception as e:
        logger.warning(f"Failed to create PID file: {e}")

    # Initialize system
    if not initialize_on_startup():
        logger.error("System initialization failed")
        sys.exit(1)

    # Start web server
    try:
        logger.info("🌐 Starting web server on port 80...")
        app.run(host="0.0.0.0", port=80, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Web server failed to start: {e}")
        sys.exit(1)
