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
    
    def configure_wifi(self, ssid: str, password: str) -> bool:
        """
        Configure WiFi connection via HA Supervisor
        
        Args:
            ssid: WiFi network SSID
            password: WiFi password
            
        Returns:
            True if configuration successful, False otherwise
        """
        try:
            logger.info(f"🔧 Configuring WiFi via HA Supervisor: {ssid}")
            
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
            
            response = requests.post(
                f"{self.base_url}/network/interface/wlan0/update",
                headers=self.headers,
                json=payload,
                timeout=60  # Connection can take time
            )
            
            if response.status_code == 200:
                logger.info(f"✅ WiFi configuration sent to HA Supervisor")
                return True
            else:
                logger.error(f"❌ Failed to configure WiFi: HTTP {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout configuring WiFi")
            return False
        except Exception as e:
            logger.error(f"❌ Error configuring WiFi: {e}")
            return False
    
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
            
            for interface in network_info.get("interfaces", []):
                if interface.get("interface") in ["eth0", "end0"]:
                    if interface.get("connected"):
                        return interface
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting Ethernet status: {e}")
            return None
