#!/usr/bin/env python3
"""
Direct gpiochip0 access test to debug permission issues
"""

import os
import stat
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_device_access():
    """Test direct access to gpiochip0"""
    device = "/dev/gpiochip0"
    
    logger.info(f"Testing direct access to {device}")
    
    # Check if device exists
    if not os.path.exists(device):
        logger.error(f"❌ {device} does not exist")
        return False
    
    # Get device stats
    try:
        stat_info = os.stat(device)
        mode = stat_info.st_mode
        permissions = stat.filemode(mode)
        owner_uid = stat_info.st_uid
        group_gid = stat_info.st_gid
        logger.info(f"📊 {device}: {permissions} (owner:{owner_uid}, group:{group_gid})")
    except Exception as e:
        logger.error(f"❌ Cannot stat {device}: {e}")
        return False
    
    # Test if we can open it for reading
    try:
        with open(device, 'rb') as f:
            logger.info(f"✅ Can open {device} for reading")
            # Try to read a small amount (this should work for GPIO chips)
            data = f.read(1)
            logger.info(f"✅ Read test successful from {device}")
            return True
    except PermissionError as e:
        logger.error(f"❌ Permission denied reading {device}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error reading {device}: {e}")
        return False

def test_lgpio_with_permissions():
    """Test lgpio with current device permissions"""
    try:
        logger.info("Testing lgpio import...")
        import lgpio
        logger.info("✅ lgpio imported successfully")
        
        # Try different gpiochip numbers (we have 0, 10, 11, 12, 13 available)
        chips_to_try = [0, 10, 11, 12, 13]
        
        for chip_num in chips_to_try:
            try:
                logger.info(f"Testing gpiochip_open({chip_num})...")
                chip = lgpio.gpiochip_open(chip_num)
                logger.info(f"✅ gpiochip_open({chip_num}) successful: {chip}")
                
                # Test basic operations on pin 17 (GPIO 17 = Physical Pin 11)
                pin = 17
                try:
                    lgpio.gpio_claim_input(chip, pin, lgpio.SET_PULL_UP)
                    logger.info(f"✅ GPIO pin {pin} claimed successfully on chip {chip_num}")
                    
                    value = lgpio.gpio_read(chip, pin)
                    logger.info(f"✅ GPIO pin {pin} read successful: {value}")
                    
                    # Cleanup
                    lgpio.gpio_free(chip, pin)
                    lgpio.gpiochip_close(chip)
                    logger.info("✅ GPIO cleanup successful")
                    
                    logger.info(f"🎉 SUCCESS: Working gpiochip found: {chip_num}")
                    return True
                    
                except Exception as pin_error:
                    logger.warning(f"⚠️  Chip {chip_num} opened but pin operations failed: {pin_error}")
                    try:
                        lgpio.gpiochip_close(chip)
                    except:
                        pass
                    continue
                    
            except Exception as chip_error:
                logger.debug(f"❌ gpiochip_open({chip_num}) failed: {chip_error}")
                continue
        
        logger.error("❌ No working gpiochip found")
        return False
        
    except ImportError as e:
        logger.error(f"❌ lgpio not available: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ lgpio test failed: {e}")
        return False

def main():
    """Run permission and access tests"""
    logger.info("=== Direct Device Access Test ===")
    
    # Test current user info
    logger.info(f"Running as UID: {os.getuid()}, GID: {os.getgid()}")
    
    # Test device access
    device_ok = test_device_access()
    
    # Test lgpio
    lgpio_ok = test_lgpio_with_permissions()
    
    if lgpio_ok:
        logger.info("🎉 SUCCESS: lgpio is working with current permissions!")
        return 0
    elif device_ok:
        logger.warning("⚠️  Device accessible but lgpio failing - library issue")
        return 1
    else:
        logger.error("❌ Device access failed - permission issue")
        return 2

if __name__ == "__main__":
    import sys
    sys.exit(main())
