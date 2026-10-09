#!/usr/bin/env python3
"""
GPIO Cleanup Script for SMASH Hub
Cleans up any existing GPIO usage to prevent 'GPIO busy' errors
"""

import logging
import os

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def cleanup_gpio_resources():
    """Clean up any existing GPIO resources that might be in use"""
    logger.info("🧹 Starting GPIO resource cleanup...")
    
    # GPIO pins used by SMASH Hub
    gpio_pins = [17, 22, 23, 24]  # Button + RGB LEDs
    
    # Try lgpio cleanup first
    try:
        import lgpio
        logger.info("🧹 Attempting lgpio cleanup...")
        
        # Try multiple chip numbers (RPi 5 compatibility)
        chips_to_try = [0, 4, 10, 11, 12, 13]
        for chip_num in chips_to_try:
            try:
                chip = lgpio.gpiochip_open(chip_num)
                for pin in gpio_pins:
                    try:
                        # Try to free the pin if it's in use
                        lgpio.gpio_free(chip, pin)
                        logger.debug(f"🧹 Freed GPIO {pin} on chip {chip_num}")
                    except:
                        pass  # Pin wasn't in use, that's fine
                lgpio.gpiochip_close(chip)
                logger.info(f"🧹 Cleaned up gpiochip{chip_num}")
            except:
                pass  # Chip not available, that's fine
                
    except ImportError:
        logger.debug("lgpio not available for cleanup")
    
    # Try gpiozero cleanup
    try:
        from gpiozero import Device
        Device.pin_factory.reset()
        logger.info("🧹 Reset gpiozero pin factory")
    except:
        logger.debug("gpiozero cleanup failed")
    
    # Try RPi.GPIO cleanup
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
        logger.info("🧹 RPi.GPIO cleanup complete")
    except:
        logger.debug("RPi.GPIO cleanup failed")
    
    # Kill any existing processes that might be using GPIO
    try:
        os.system("pkill -f led_controller 2>/dev/null || true")
        os.system("pkill -f button_monitor 2>/dev/null || true")
        logger.info("🧹 Killed existing GPIO processes")
    except:
        pass
    
    logger.info("✅ GPIO cleanup complete")

if __name__ == "__main__":
    cleanup_gpio_resources()
