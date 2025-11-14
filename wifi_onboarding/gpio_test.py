#!/usr/bin/env python3
"""
GPIO Hardware Test Script for SMASH Hub
Tests GPIO functionality for button and LED hardware
Based on the working reference implementation
"""

import time
import subprocess
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def test_gpio_device_access():
    """Test access to GPIO devices"""
    logger.info("=== Testing GPIO Device Access ===")
    
    # Check for GPIO devices that should be available in container
    gpio_devices = [
        "/dev/gpiomem",
        "/dev/gpiochip0", "/dev/gpiochip1", "/dev/gpiochip4", 
        "/dev/gpiochip10", "/dev/gpiochip11", "/dev/gpiochip12", "/dev/gpiochip13",
        "/dev/mem"
    ]
    
    available_devices = []
    
    for device in gpio_devices:
        if os.path.exists(device):
            try:
                stat_info = os.stat(device)
                readable = os.access(device, os.R_OK)
                writable = os.access(device, os.W_OK)
                logger.info(f"✅ {device} - exists (R:{readable}, W:{writable}, mode:{oct(stat_info.st_mode)})")
                available_devices.append(device)
            except Exception as e:
                logger.info(f"❌ {device} - access error: {e}")
        else:
            logger.info(f"❌ {device} - not found")
    
    return available_devices

def test_gpio_libraries():
    """Test GPIO library imports and basic functionality"""
    logger.info("=== Testing GPIO Libraries ===")
    
    working_libraries = []
    
    # Test lgpio (primary for RPi 5)
    try:
        import lgpio
        logger.info("✅ lgpio library imported successfully")
        
        # Test opening GPIO chips
        for chip_num in [0, 4, 10, 11, 12, 13]:
            try:
                chip = lgpio.gpiochip_open(chip_num)
                logger.info(f"  ✅ gpiochip{chip_num} opened successfully")
                lgpio.gpiochip_close(chip)
                working_libraries.append(f"lgpio-chip{chip_num}")
                break  # Found working chip
            except Exception as e:
                logger.debug(f"  ❌ gpiochip{chip_num} failed: {e}")
                continue
        
    except ImportError as e:
        logger.info(f"❌ lgpio library not available: {e}")
    except Exception as e:
        logger.info(f"❌ lgpio library error: {e}")

    # Test gpiozero (secondary)
    try:
        # Force native pin factory for container compatibility
        os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
        from gpiozero import Device, LED, Button
        logger.info("✅ gpiozero library imported successfully")
        
        # Test pin factory
        try:
            logger.info(f"  Pin factory: {Device.pin_factory}")
            working_libraries.append("gpiozero")
        except Exception as e:
            logger.info(f"  ❌ gpiozero pin factory error: {e}")
            
    except ImportError as e:
        logger.info(f"❌ gpiozero library not available: {e}")
    except Exception as e:
        logger.info(f"❌ gpiozero library error: {e}")

    # Test RPi.GPIO (legacy)
    try:
        import RPi.GPIO as GPIO
        logger.info("✅ RPi.GPIO library imported successfully")
        working_libraries.append("RPi.GPIO")
    except ImportError as e:
        logger.info(f"❌ RPi.GPIO library not available: {e}")
    except Exception as e:
        logger.info(f"❌ RPi.GPIO library error: {e}")

    return working_libraries

def test_button_gpio(pin=17):
    """Test button GPIO functionality using proven working approach"""
    logger.info(f"=== Testing Button GPIO (Pin {pin}) ===")
    
    # Test lgpio approach first
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(chip, pin, lgpio.SET_PULL_UP)
        
        logger.info(f"✅ Button GPIO {pin} configured with lgpio")
        
        # Test reading for 5 seconds
        logger.info("Testing button reading for 5 seconds (press button to test)...")
        for i in range(5):
            value = lgpio.gpio_read(chip, pin)
            state = "PRESSED" if value == 0 else "RELEASED"  # Active low with pull-up
            logger.info(f"  Second {i+1}: GPIO {pin} = {value} ({state})")
            time.sleep(1)
        
        lgpio.gpiochip_close(chip)
        return True
        
    except Exception as e:
        logger.info(f"❌ lgpio button test failed: {e}")

    # Test gpiozero approach
    try:
        os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
        from gpiozero import Button
        
        button = Button(pin, pull_up=True, bounce_time=0.1)
        logger.info(f"✅ Button GPIO {pin} configured with gpiozero")
        
        # Test reading for 5 seconds
        logger.info("Testing button reading for 5 seconds (press button to test)...")
        for i in range(5):
            pressed = button.is_pressed
            state = "PRESSED" if pressed else "RELEASED"
            logger.info(f"  Second {i+1}: Button {pin} = {state}")
            time.sleep(1)
        
        button.close()
        return True
        
    except Exception as e:
        logger.info(f"❌ gpiozero button test failed: {e}")

    return False

def test_led_gpio(red_pin=22, green_pin=23, blue_pin=24):
    """Test LED GPIO functionality using proven working approach"""
    logger.info(f"=== Testing LED GPIO (R:{red_pin}, G:{green_pin}, B:{blue_pin}) ===")
    
    led_pins = {'red': red_pin, 'green': green_pin, 'blue': blue_pin}
    
    # Test lgpio approach first
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        
        # Configure all LED pins as outputs
        for color, pin in led_pins.items():
            lgpio.gpio_claim_output(chip, pin)
            lgpio.gpio_write(chip, pin, 0)  # Start with LED off
        
        logger.info(f"✅ LED GPIOs configured with lgpio")
        
        # Test LED sequence
        logger.info("Testing LED sequence (2 seconds each)...")
        
        for color, pin in led_pins.items():
            logger.info(f"  Turning on {color.upper()} LED (GPIO {pin})...")
            lgpio.gpio_write(chip, pin, 1)
            time.sleep(2)
            lgpio.gpio_write(chip, pin, 0)
            time.sleep(0.5)
        
        # Test blinking
        logger.info("  Testing red blink pattern...")
        for i in range(5):
            lgpio.gpio_write(chip, red_pin, 1)
            time.sleep(0.3)
            lgpio.gpio_write(chip, red_pin, 0)
            time.sleep(0.3)
        
        # Clean up
        for color, pin in led_pins.items():
            lgpio.gpio_write(chip, pin, 0)
        
        lgpio.gpiochip_close(chip)
        return True
        
    except Exception as e:
        logger.info(f"❌ lgpio LED test failed: {e}")

    # Test gpiozero approach
    try:
        os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
        from gpiozero import LED
        
        leds = {}
        for color, pin in led_pins.items():
            leds[color] = LED(pin)
            leds[color].off()
        
        logger.info(f"✅ LED GPIOs configured with gpiozero")
        
        # Test LED sequence
        logger.info("Testing LED sequence (2 seconds each)...")
        
        for color, led in leds.items():
            logger.info(f"  Turning on {color.upper()} LED...")
            led.on()
            time.sleep(2)
            led.off()
            time.sleep(0.5)
        
        # Test blinking
        logger.info("  Testing red blink pattern...")
        for i in range(5):
            leds['red'].on()
            time.sleep(0.3)
            leds['red'].off()
            time.sleep(0.3)
        
        # Clean up
        for led in leds.values():
            led.close()
        
        return True
        
    except Exception as e:
        logger.info(f"❌ gpiozero LED test failed: {e}")

    return False

def test_container_permissions():
    """Test container permissions and system access"""
    logger.info("=== Testing Container Permissions ===")
    
    # Test system commands that GPIO libraries might need
    commands_to_test = [
        ("ls /dev/gpio*", "GPIO devices visibility"),
        ("ls /sys/class/gpio", "GPIO sysfs access"),
        ("cat /proc/cpuinfo | grep Hardware", "Hardware detection"),
        ("uname -a", "Kernel version"),
    ]
    
    for cmd, description in commands_to_test:
        try:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info(f"✅ {description}: {result.stdout.strip()}")
            else:
                logger.info(f"❌ {description}: {result.stderr.strip()}")
        except Exception as e:
            logger.info(f"❌ {description}: {e}")

def main():
    """Run comprehensive GPIO hardware tests"""
    logger.info("🔬 Starting GPIO Hardware Diagnostics")
    logger.info("=" * 50)
    
    # Get configuration from environment or defaults
    gpio_pin = int(os.getenv('GPIO_PIN', '17'))
    led_red_pin = int(os.getenv('LED_RED_PIN', '22'))
    led_green_pin = int(os.getenv('LED_GREEN_PIN', '23'))
    led_blue_pin = int(os.getenv('LED_BLUE_PIN', '24'))
    
    logger.info(f"Configuration: Button GPIO {gpio_pin}, LEDs R:{led_red_pin} G:{led_green_pin} B:{led_blue_pin}")
    
    # Run all tests
    available_devices = test_gpio_device_access()
    working_libraries = test_gpio_libraries()
    test_container_permissions()
    
    # Only proceed with hardware tests if we have devices and libraries
    if available_devices and working_libraries:
        logger.info("\n" + "=" * 50)
        logger.info("🔬 HARDWARE TESTS")
        
        button_works = test_button_gpio(gpio_pin)
        led_works = test_led_gpio(led_red_pin, led_green_pin, led_blue_pin)
        
        logger.info("\n" + "=" * 50)
        logger.info("📊 SUMMARY")
        logger.info(f"Available GPIO devices: {len(available_devices)}")
        logger.info(f"Working GPIO libraries: {working_libraries}")
        logger.info(f"Button GPIO {gpio_pin}: {'✅ WORKING' if button_works else '❌ FAILED'}")
        logger.info(f"LED GPIOs: {'✅ WORKING' if led_works else '❌ FAILED'}")
        
        if button_works and led_works:
            logger.info("🎉 All GPIO hardware tests PASSED!")
            return 0
        else:
            logger.info("⚠️ Some GPIO hardware tests FAILED!")
            return 1
    else:
        logger.info("❌ Cannot run hardware tests - no GPIO devices or libraries available")
        logger.info(f"Available devices: {available_devices}")
        logger.info(f"Working libraries: {working_libraries}")
        return 1

def check_gpio_devices():
    """Check GPIO device availability and system information"""
    logger.info("🔍 Checking GPIO devices and system information...")
    
    # Check for gpiochip devices
    gpio_devices = []
    try:
        for i in range(5):  # Check for up to 5 GPIO chips
            device_path = f'/dev/gpiochip{i}'
            if os.path.exists(device_path):
                gpio_devices.append(device_path)
        
        if gpio_devices:
            logger.info(f"✅ Found GPIO devices: {gpio_devices}")
        else:
            logger.warning("❌ No gpiochip devices found")
    except Exception as e:
        logger.warning(f"⚠️ Error checking GPIO devices: {e}")
    
    # Check current user/group information
    try:
        import pwd, grp
        user = pwd.getpwuid(os.getuid()).pw_name
        groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
        logger.info(f"� Running as user: {user}, groups: {groups}")
    except:
        logger.info(f"🔍 Running as UID: {os.getuid()}, GID: {os.getgid()}")
    
    # Check for GPIO-related kernel modules
    try:
        result = subprocess.run(['lsmod'], capture_output=True, text=True)
        gpio_modules = [line for line in result.stdout.split('\n') if 'gpio' in line.lower()]
        if gpio_modules:
            logger.info("🔍 GPIO kernel modules found:")
            for module in gpio_modules[:5]:  # Show first 5
                logger.info(f"  {module}")
        else:
            logger.warning("⚠️ No GPIO kernel modules found")
    except Exception as e:
        logger.warning(f"⚠️ Could not check kernel modules: {e}")
    
    # Check if running in container
    if os.path.exists('/.dockerenv'):
        logger.info("🐳 Running in Docker container")
    else:
        logger.info("💻 Running on host system")

if __name__ == "__main__":
    sys.exit(main())
