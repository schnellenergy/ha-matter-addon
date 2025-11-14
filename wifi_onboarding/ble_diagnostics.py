#!/usr/bin/env python3
"""
Simple BLE test script to verify D-Bus and BlueZ functionality
"""

import sys
import logging
import subprocess
import os

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_dbus():
    """Test D-Bus availability"""
    # First try system packages with correct Python paths
    import sys
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    sys.path.insert(0, '/usr/lib/python3.13/dist-packages')
    
    try:
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
        logger.info("✅ D-Bus libraries available (system packages)")
        logger.info(f"dbus module from: {dbus.__file__}")
        return True
    except ImportError as e:
        logger.error(f"❌ D-Bus libraries not available: {e}")
        logger.info("Available system packages:")
        try:
            import os
            for path in ['/usr/lib/python3/dist-packages', '/usr/lib/python3.13/dist-packages']:
                if os.path.exists(path):
                    packages = os.listdir(path)
                    dbus_packages = [p for p in packages if 'dbus' in p.lower() or 'gi' in p.lower()]
                    logger.info(f"In {path}:")
                    for pkg in dbus_packages:
                        logger.info(f"  - {pkg}")
        except Exception as pkg_error:
            logger.error(f"Could not list packages: {pkg_error}")
        return False

def test_bluez():
    """Test BlueZ availability"""
    # Use system packages with correct Python paths
    import sys
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    sys.path.insert(0, '/usr/lib/python3.13/dist-packages')
    
    try:
        import dbus
        bus = dbus.SystemBus()
        bluez_obj = bus.get_object('org.bluez', '/')
        logger.info("✅ BlueZ D-Bus service is running")
        return True
    except Exception as e:
        logger.error(f"❌ BlueZ not available: {e}")
        return False

def test_hci():
    """Test Bluetooth adapter"""
    try:
        result = subprocess.run(['hciconfig'], capture_output=True, text=True)
        if result.returncode == 0 and 'hci0' in result.stdout:
            logger.info("✅ Bluetooth adapter available")
            logger.info(f"HCI info:\n{result.stdout}")
            return True
        else:
            logger.error("❌ No Bluetooth adapter found")
            return False
    except Exception as e:
        logger.error(f"❌ Error checking Bluetooth adapter: {e}")
        return False

def run_diagnostics():
    """Run comprehensive BLE diagnostics"""
    logger.info("🔍 Running BLE Diagnostics...")
    
    # Check environment
    logger.info("📋 Environment Check:")
    logger.info(f"  Python version: {sys.version}")
    logger.info(f"  UID: {os.getuid()}")
    logger.info(f"  DBUS_SYSTEM_BUS_ADDRESS: {os.environ.get('DBUS_SYSTEM_BUS_ADDRESS', 'not set')}")
    
    # Test components
    results = {
        'dbus': test_dbus(),
        'bluez': test_bluez(),
        'hci': test_hci()
    }
    
    logger.info("\n📊 Test Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    logger.info(f"\n🎯 Overall Status: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        logger.info("🚀 System is ready for BLE onboarding!")
    else:
        logger.info("🔧 Please fix the failing components before starting BLE service")
    
    return all_passed

if __name__ == '__main__':
    success = run_diagnostics()
    sys.exit(0 if success else 1)
