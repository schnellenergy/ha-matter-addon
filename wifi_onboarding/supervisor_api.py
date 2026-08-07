#!/usr/bin/env python3
"""
Home Assistant Supervisor API Helper
Provides a clean interface for managing WiFi connections via HA Supervisor API
"""

import os
import time
import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SupervisorAPI:
    """Helper class for Home Assistant Supervisor API calls"""
    
    def __init__(self):
        self.base_url = "http://supervisor"
        self.token = os.getenv("SUPERVISOR_TOKEN")
        
        if not self.token:
            logger.warning("⚠️ SUPERVISOR_TOKEN not found in environment")
            logger.warning("   API calls may fail - ensure addon has proper permissions")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # Test API connectivity on initialization
        self._test_connectivity()
    
    def _test_connectivity(self):
        """Test if Supervisor API is accessible"""
        try:
            response = requests.get(
                f"{self.base_url}/network/info",
                headers=self.headers,
                timeout=5
            )
            if response.status_code == 200:
                logger.info("✅ Home Assistant Supervisor API is accessible")
                return True
            else:
                logger.warning(f"⚠️ Supervisor API returned status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Cannot connect to Supervisor API: {e}")
            logger.error("   Ensure addon is running in Home Assistant OS environment")
            return False
    
    def get_network_info(self) -> Optional[Dict]:
        """
        Get current network status for all interfaces
        
        Returns:
            Dict with network information or None on error
        """
        try:
            logger.debug("📡 Fetching network info from Supervisor API...")
            response = requests.get(
                f"{self.base_url}/network/info",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"✅ Network info retrieved: {len(data.get('interfaces', []))} interfaces")
                return data
            else:
                logger.error(f"❌ Failed to get network info: HTTP {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout getting network info from Supervisor API")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting network info: {e}")
            return None
    
    def get_wifi_networks(self) -> Optional[Dict]:
        """
        Get available WiFi access points
        
        Returns:
            Dict with list of access points or None on error
        """
        try:
            logger.info("📡 Scanning for WiFi networks via Supervisor API...")
            response = requests.get(
                f"{self.base_url}/network/interface/wlan0/accesspoints",
                headers=self.headers,
                timeout=30  # Scanning takes time
            )
            
            if response.status_code == 200:
                data = response.json()
                networks = data.get('accesspoints', [])
                logger.info(f"✅ Found {len(networks)} WiFi networks")
                return data
            else:
                logger.error(f"❌ Failed to scan WiFi networks: HTTP {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout scanning WiFi networks")
            return None
        except Exception as e:
            logger.error(f"❌ Error scanning WiFi networks: {e}")
            return None
    
    # NetworkManager errors that mean "stale internal state", not "bad
    # credentials". They happen when a profile was just torn down and NM is still
    # settling — retrying after a pause clears them, whereas failing outright
    # leaves the user unable to onboard for minutes after a reset.
    # Genuinely transient: NetworkManager has not finished releasing a previous
    # profile. Retrying after a pause clears these.
    _TRANSIENT_NM_ERRORS = (
        'object does not exist',            # stale ActiveConnection D-Bus path
        'device is not ready',
        'not managed',
        'unknown connection',
    )

    # NetworkManager's way of saying the credentials were rejected.
    #
    # "Activating connection failed" was previously treated as transient and
    # retried three times. That is exactly what a WRONG PASSWORD produces, so a
    # rejected password took ~3 x (7s + 4s) before being reported — and was then
    # reported as a generic network error rather than a bad password. It fails
    # fast and honestly now.
    _AUTH_NM_ERRORS = (
        'activating connection failed',
        'secrets were required',
        'no secrets provided',
        'invalid psk',
        'psk',
    )

    def configure_wifi(self, ssid: str, password: str, max_attempts: int = 3) -> Dict:
        """
        Configure WiFi connection via HA Supervisor.

        Retries transient NetworkManager failures. Right after a network reset NM
        can reject the activation with "Activating connection failed" or a stale
        "Object does not exist at path .../ActiveConnection/N" — the interface is
        fine, NM just has not finished tearing the old profile down. A single
        attempt turned that into a hard provisioning failure.

        Args:
            ssid: WiFi network SSID
            password: WiFi password
            max_attempts: attempts for transient NM errors

        Returns:
            {'ok': bool, 'reason': None | 'auth_failed' | 'network_error'}
        """
        payload = {
            "ipv4": {
                "method": "auto",
                "nameservers": []
            },
            "ipv6": {
                "method": "auto",
                "nameservers": []
            },
            "wifi": {
                "ssid": ssid,
                "mode": "infrastructure",
                "auth": "wpa-psk",
                "psk": password
            },
            "enabled": True
        }

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"🔧 Configuring WiFi via HA Supervisor: {ssid} "
                    f"(attempt {attempt}/{max_attempts})")

                response = requests.post(
                    f"{self.base_url}/network/interface/wlan0/update",
                    headers=self.headers,
                    json=payload,
                    timeout=60  # Connection can take time
                )

                if response.status_code == 200:
                    logger.info(f"✅ WiFi configuration sent to HA Supervisor")
                    return {'ok': True, 'reason': None}

                body = (response.text or '').lower()
                logger.error(f"❌ Failed to configure WiFi: HTTP {response.status_code}")
                logger.error(f"   Response: {response.text}")

                # Rejected credentials: report at once, no retry. Retrying a
                # wrong password only makes the user wait.
                if any(marker in body for marker in self._AUTH_NM_ERRORS):
                    logger.error("❌ NetworkManager rejected the credentials")
                    return {'ok': False, 'reason': 'auth_failed'}

                if (not any(m in body for m in self._TRANSIENT_NM_ERRORS)
                        or attempt == max_attempts):
                    return {'ok': False, 'reason': 'network_error'}

                # Give NM a moment to finish releasing the previous profile.
                logger.warning(
                    "⚠️ NetworkManager is still settling after the previous "
                    "profile — waiting 4s and retrying")
                time.sleep(4)

            except requests.exceptions.Timeout:
                logger.error("❌ Timeout configuring WiFi")
                return {'ok': False, 'reason': 'network_error'}
            except Exception as e:
                logger.error(f"❌ Error configuring WiFi: {e}")
                return {'ok': False, 'reason': 'network_error'}

        return {'ok': False, 'reason': 'network_error'}


    def disconnect_wifi(self) -> bool:
        """
        Disconnect WiFi (network reset)
        
        Returns:
            True if disconnect successful, False otherwise
        """
        try:
            logger.info("🔄 Disconnecting WiFi via HA Supervisor...")
            
            payload = {
                "ipv4": {
                    "method": "auto",
                    "nameservers": []
                },
                "ipv6": {
                    "method": "auto",
                    "nameservers": []
                },
                "enabled": False  # CRITICAL: False to disable WiFi interface
            }
            
            response = requests.post(
                f"{self.base_url}/network/interface/wlan0/update",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("✅ WiFi disconnected via HA Supervisor")
                return True
            else:
                logger.error(f"❌ Failed to disconnect WiFi: HTTP {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout disconnecting WiFi")
            return False
        except Exception as e:
            logger.error(f"❌ Error disconnecting WiFi: {e}")
            return False

    # NOTE: `enabled: False` is what actually forgets the network. Home Assistant
    # Supervisor deletes the interface's connection settings when an update
    # disables it, so this removes the saved Wi-Fi from Home Assistant itself —
    # not merely switching the radio off.
    #
    # A previous revision replaced this with `enabled: True` and no `wifi` block,
    # on the assumption that omitting `wifi` meant "forget it". That assumption
    # was wrong: an omitted field is left UNCHANGED, so the saved network would
    # have survived every reset. Reverted, and kept as-is deliberately.

    def get_wlan0_status(self) -> Optional[Dict]:
        """
        Get wlan0 interface status
        
        Returns:
            Dict with wlan0 interface info or None if not found
        """
        try:
            network_info = self.get_network_info()
            if not network_info:
                return None
            
            # Parse interfaces array from Supervisor API response
            interfaces = network_info.get('data', {}).get('interfaces', [])
            if not interfaces:
                # Try alternate format
                interfaces = network_info.get('interfaces', [])
            
            for interface in interfaces:
                if interface.get("interface") == "wlan0":
                    return interface
            
            logger.warning("⚠️ wlan0 interface not found in network info")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting wlan0 status: {e}")
            return None
    
    def wait_for_wifi_connection(self, timeout: int = 30) -> Optional[str]:
        """
        Wait for WiFi connection and return assigned IP address
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            IP address if connected, None if timeout or error
        """
        logger.info(f"⏳ Waiting for WiFi connection (timeout: {timeout}s)...")
        
        start_time = time.time()
        attempt = 0
        
        while (time.time() - start_time) < timeout:
            attempt += 1
            
            try:
                wlan0_status = self.get_wlan0_status()
                
                if wlan0_status and wlan0_status.get("connected"):
                    # Extract IP address
                    ipv4_addresses = wlan0_status.get("ipv4", {}).get("address", [])
                    if ipv4_addresses:
                        # IP format: "192.168.1.100/24" - extract just the IP
                        ip_with_subnet = ipv4_addresses[0]
                        ip_address = ip_with_subnet.split("/")[0]
                        
                        ssid = wlan0_status.get("wifi", {}).get("ssid", "Unknown")
                        logger.info(f"✅ WiFi connected to '{ssid}' with IP: {ip_address}")
                        return ip_address
                    else:
                        logger.debug(f"Attempt {attempt}: Connected but no IP assigned yet")
                else:
                    logger.debug(f"Attempt {attempt}: Not connected yet")
                
            except Exception as e:
                logger.debug(f"Attempt {attempt}: Error checking status: {e}")
            
            time.sleep(1)
        
        logger.error(f"❌ WiFi connection timeout after {timeout}s")
        return None
    
    def wait_for_connection_phased(
        self,
        expected_ssid: str,
        assoc_timeout: int = 20,
        dhcp_timeout: int = 40,
    ) -> Dict:
        """Wait for wlan0 in two distinct phases and report which one failed.

        `wait_for_wifi_connection` collapses association and DHCP into one
        timeout, so every failure looked identical and got reported to the app
        as "re-enter your password" — including slow-DHCP failures on a
        perfectly correct password. Supervisor already exposes the two facts
        separately (`connected` and `ipv4.address`), so we can separate them:

          phase 1  not associated within assoc_timeout  -> wrong passphrase
          phase 2  associated but no IPv4 within dhcp_timeout -> DHCP/router

        Splitting also lets phase 1 stay short, so a genuinely wrong password
        is reported in ~20 s instead of waiting out the full budget.

        Returns {'ip': str|None, 'reason': None|'auth_failed'|'no_ip',
                 'ssid': str|None}.
        """
        logger.info(
            f"⏳ Waiting for WiFi: association ≤{assoc_timeout}s, then IP ≤{dhcp_timeout}s"
        )

        associated = False
        ssid = None

        # Phase 1 — association WITH THE REQUESTED NETWORK.
        #
        # Checking only `connected` is not enough. When a hub is already on a
        # network and is then given wrong credentials, NetworkManager keeps the
        # previous connection up while the new one fails — so wlan0 still reports
        # connected, still holds its old IP, and a bare `connected` check reports
        # SUCCESS for a password that was rejected. That is what turned the LED
        # blue on a wrong password. Requiring the SSID to be the one we asked for
        # makes the check mean what it says.
        assoc_deadline = time.time() + assoc_timeout
        while time.time() < assoc_deadline:
            status = self.get_wlan0_status()
            current_ssid = (status or {}).get("wifi", {}).get("ssid")
            if status and status.get("connected") and current_ssid == expected_ssid:
                associated = True
                ssid = current_ssid
                logger.info(f"✅ Associated with '{ssid}' — waiting for IP address")

                # Association and DHCP often complete together; if the address
                # is already present, skip straight out.
                addresses = status.get("ipv4", {}).get("address", [])
                if addresses:
                    ip = addresses[0].split("/")[0]
                    logger.info(f"✅ WiFi connected with IP: {ip}")
                    return {'ip': ip, 'reason': None, 'ssid': ssid}
                break
            time.sleep(1)

        if not associated:
            logger.error(
                f"❌ wlan0 did not join '{expected_ssid}' within {assoc_timeout}s — "
                "treating as authentication failure"
            )
            return {'ip': None, 'reason': 'auth_failed', 'ssid': None}

        # Phase 2 — DHCP.
        dhcp_deadline = time.time() + dhcp_timeout
        while time.time() < dhcp_deadline:
            status = self.get_wlan0_status()
            current_ssid = (status or {}).get("wifi", {}).get("ssid")
            if status and status.get("connected") and current_ssid == expected_ssid:
                addresses = status.get("ipv4", {}).get("address", [])
                if addresses:
                    ip = addresses[0].split("/")[0]
                    logger.info(f"✅ WiFi connected with IP: {ip}")
                    return {'ip': ip, 'reason': None, 'ssid': ssid}
            else:
                # Dropped off the requested network after initially joining it —
                # an authentication problem, not a DHCP one.
                logger.error(
                    f"❌ wlan0 left '{expected_ssid}' while waiting for IP "
                    f"(now on {current_ssid!r})")
                return {'ip': None, 'reason': 'auth_failed', 'ssid': ssid}
            time.sleep(1)

        logger.error(f"❌ Associated but no IPv4 address within {dhcp_timeout}s")
        return {'ip': None, 'reason': 'no_ip', 'ssid': ssid}

    def get_ethernet_status(self) -> Optional[Dict]:
        """
        Get Ethernet interface status (eth0 or end0)
        
        Returns:
            Dict with Ethernet interface info or None if not found/connected
        """
        try:
            network_info = self.get_network_info()
            if not network_info:
                return None

            # Same two response shapes get_wlan0_status already handles; this
            # method only checked the un-nested one, so on a Supervisor build
            # that nests under `data` it always reported "no ethernet".
            interfaces = network_info.get('data', {}).get('interfaces', [])
            if not interfaces:
                interfaces = network_info.get('interfaces', [])

            for interface in interfaces:
                if interface.get("interface") in ["eth0", "end0"]:
                    if interface.get("connected"):
                        return interface

            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting Ethernet status: {e}")
            return None
