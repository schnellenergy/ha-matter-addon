#!/usr/bin/env python3
"""
Simple GPIO Hardware Test for SMASH Hub
Quick test to verify button and LED functionality
"""

import os
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def test_button_simple(pin=17):
    """Test button using the simplest approach that works"""
    logger.info(f"Testing button on GPIO {pin}")
    
    # Try lgpio first (RPi 5)
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(chip, pin, lgpio.SET_PULL_UP)
        
        logger.info("✅ Button configured with lgpio - press button for 5 seconds...")
        for i in range(5):
            value = lgpio.gpio_read(chip, pin)
            state = "PRESSED" if value == 0 else "released"
            logger.info(f"  {i+1}/5: {state}")
            time.sleep(1)
        
        lgpio.gpiochip_close(chip)
        return True
        
    except Exception as e:
        logger.info(f"lgpio failed: {e}")

    # Try gpiozero
    try:
        os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
        from gpiozero import Button
        
        button = Button(pin, pull_up=True, bounce_time=0.1)
        logger.info("✅ Button configured with gpiozero - press button for 5 seconds...")
        
        for i in range(5):
            state = "PRESSED" if button.is_pressed else "released"
            logger.info(f"  {i+1}/5: {state}")
            time.sleep(1)
        
        button.close()
        return True
        
    except Exception as e:
        logger.info(f"gpiozero failed: {e}")

    logger.error("❌ All button test methods failed")
    return False

def test_leds_simple(red_pin=22, green_pin=23, blue_pin=24):
    """Test LEDs using the simplest approach that works"""
    logger.info(f"Testing LEDs - Red:{red_pin}, Green:{green_pin}, Blue:{blue_pin}")
    
    # Try lgpio first (RPi 5)
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        
        # Configure all pins
        pins = {'Red': red_pin, 'Green': green_pin, 'Blue': blue_pin}
        for color, pin in pins.items():
            lgpio.gpio_claim_output(chip, pin)
            lgpio.gpio_write(chip, pin, 0)  # Start off
        
        logger.info("✅ LEDs configured with lgpio")
        
        # Test each LED
        for color, pin in pins.items():
            logger.info(f"  Turning on {color} LED...")
            lgpio.gpio_write(chip, pin, 1)
            time.sleep(2)
            lgpio.gpio_write(chip, pin, 0)
        
        # Test blink pattern
        logger.info("  Testing blink pattern...")
        for i in range(6):
            lgpio.gpio_write(chip, red_pin, 1)
            time.sleep(0.5)
            lgpio.gpio_write(chip, red_pin, 0)
            time.sleep(0.5)
        
        lgpio.gpiochip_close(chip)
        return True
        
    except Exception as e:
        logger.info(f"lgpio LED test failed: {e}")

    # Try gpiozero
    try:
        os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
        from gpiozero import LED
        
        leds = {
            'Red': LED(red_pin),
            'Green': LED(green_pin), 
            'Blue': LED(blue_pin)
        }
        
        logger.info("✅ LEDs configured with gpiozero")
        
        # Test each LED
        for color, led in leds.items():
            logger.info(f"  Turning on {color} LED...")
            led.on()
            time.sleep(2)
            led.off()
        
        # Test blink pattern
        logger.info("  Testing blink pattern...")
        for i in range(6):
            leds['Red'].on()
            time.sleep(0.5)
            leds['Red'].off()
            time.sleep(0.5)
        
        # Cleanup
        for led in leds.values():
            led.close()
        
        return True
        
    except Exception as e:
        logger.info(f"gpiozero LED test failed: {e}")

    logger.error("❌ All LED test methods failed")
    return False

def main():
    """Run simple GPIO hardware tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test GPIO functionality')
    parser.add_argument('--quick', action='store_true', help='Quick test mode (shorter duration)')
    args = parser.parse_args()
    
    if args.quick:
        logger.info("🏃 Quick GPIO hardware test mode")
    else:
        logger.info("🔧 Starting Simple GPIO Hardware Test")
    
    # Test GPIO library imports first
    lgpio_ok = False
    gpiozero_ok = False
    
    try:
        import lgpio
        logger.info("✅ lgpio import successful")
        lgpio_ok = True
    except ImportError as e:
        logger.warning(f"❌ lgpio import failed: {e}")
    
    try:
        import gpiozero
        logger.info("✅ gpiozero import successful")
        gpiozero_ok = True
    except ImportError as e:
        logger.warning(f"❌ gpiozero import failed: {e}")
    
    if not lgpio_ok and not gpiozero_ok:
        logger.error("❌ No GPIO libraries available - GPIO hardware cannot be controlled")
        return 1
    
    # Test button
    button_ok = test_button_simple()
    
    # Test LEDs  
    leds_ok = test_leds_simple()
    
    # Summary
    if button_ok and leds_ok:
        logger.info("✅ All GPIO tests passed!")
        return 0
    else:
        logger.error("❌ Some GPIO tests failed")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
