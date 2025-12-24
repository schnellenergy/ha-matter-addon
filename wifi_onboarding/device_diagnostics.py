#!/usr/bin/env python3
"""
Comprehensive device diagnostics script for GPIO troubleshooting
Based on successful reference implementation patterns
"""

import os
import sys
import subprocess
import logging
import stat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(cmd, timeout=10):
    """Run command with error handling"""
    try:
        if isinstance(cmd, str):
            result = subprocess.run(cmd, shell=True, capture_output=True, 
                                  text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, capture_output=True, 
                                  text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def check_device_access():
    """Check device access like the reference implementation"""
    logger.info("=== Device Access Diagnostics ===")
    
    # Check if we're running as root
    logger.info(f"Running as UID: {os.getuid()}, GID: {os.getgid()}")
    logger.info(f"Effective UID: {os.geteuid()}, Effective GID: {os.getegid()}")
    
    # Check for GPIO devices
    gpio_devices = [
        "/dev/gpiomem",
        "/dev/gpiomem0", 
        "/dev/mem",
        "/dev/gpiochip0",
        "/dev/gpiochip1",
        "/dev/gpiochip2",
        "/dev/gpiochip3",
        "/dev/gpiochip4"
    ]
    
    for device in gpio_devices:
        if os.path.exists(device):
            try:
                stat_info = os.stat(device)
                mode = stat_info.st_mode
                permissions = stat.filemode(mode)
                owner_uid = stat_info.st_uid
                group_gid = stat_info.st_gid
                logger.info(f"✅ {device}: {permissions} (owner:{owner_uid}, group:{group_gid})")
                
                # Check read/write access
                readable = os.access(device, os.R_OK)
                writable = os.access(device, os.W_OK)
                logger.info(f"   Access: R={readable}, W={writable}")
                
            except Exception as e:
                logger.error(f"❌ {device}: Error checking stats - {e}")
        else:
            logger.warning(f"❌ {device}: Missing")
    
    # Check /sys/class/gpio
    gpio_sysfs = "/sys/class/gpio"
    if os.path.exists(gpio_sysfs):
        logger.info(f"✅ {gpio_sysfs}: Available")
        export_file = f"{gpio_sysfs}/export"
        if os.path.exists(export_file):
            writable = os.access(export_file, os.W_OK)
            logger.info(f"   export file writable: {writable}")
        
        # List available gpiochips
        try:
            chips = [f for f in os.listdir(gpio_sysfs) if f.startswith('gpiochip')]
            logger.info(f"   Available gpiochips: {chips}")
        except Exception as e:
            logger.error(f"   Error listing gpiochips: {e}")
    else:
        logger.warning(f"❌ {gpio_sysfs}: Missing")

def check_kernel_modules():
    """Check if required kernel modules are loaded"""
    logger.info("=== Kernel Modules ===")
    
    required_modules = [
        "gpio_bcm2835",
        "bcm2835_gpiomem", 
        "i2c_bcm2835",
        "spi_bcm2835"
    ]
    
    # Get loaded modules
    rc, stdout, stderr = run_command("lsmod")
    if rc == 0:
        loaded_modules = stdout.lower()
        for module in required_modules:
            if module in loaded_modules:
                logger.info(f"✅ {module}: Loaded")
            else:
                logger.warning(f"❌ {module}: Not loaded")
    else:
        logger.error(f"Failed to check modules: {stderr}")

def check_device_permissions():
    """Check and attempt to fix device permissions"""
    logger.info("=== Device Permission Fixes ===")
    
    # Check if we can create /dev/gpiomem if missing
    if not os.path.exists("/dev/gpiomem"):
        # Check if gpiomem0 exists and symlink it
        if os.path.exists("/dev/gpiomem0"):
            try:
                os.symlink("/dev/gpiomem0", "/dev/gpiomem")
                logger.info("✅ Created /dev/gpiomem -> /dev/gpiomem0 symlink")
            except Exception as e:
                logger.error(f"❌ Failed to create gpiomem symlink: {e}")
    
    # Try to change permissions on key devices
    devices_to_fix = ["/dev/gpiomem", "/dev/gpiomem0", "/dev/mem"]
    for device in devices_to_fix:
        if os.path.exists(device):
            try:
                # Try to make it readable/writable for root
                os.chmod(device, 0o666)
                logger.info(f"✅ Updated permissions for {device}")
            except Exception as e:
                logger.debug(f"Could not update permissions for {device}: {e}")

def test_gpio_libraries():
    """Test GPIO library availability and basic functionality"""
    logger.info("=== GPIO Library Tests ===")
    
    # Test lgpio
    try:
        import lgpio
        logger.info("✅ lgpio: Import successful")
        try:
            chip = lgpio.gpiochip_open(0)
            logger.info("✅ lgpio: Can open chip 0")
            lgpio.gpiochip_close(chip)
        except Exception as e:
            logger.warning(f"❌ lgpio: Cannot open chip - {e}")
    except ImportError:
        logger.warning("❌ lgpio: Not available")
    
    # Test gpiozero
    try:
        import gpiozero
        logger.info("✅ gpiozero: Import successful")
        # Test pin factory
        try:
            from gpiozero.pins.native import NativeFactory
            factory = NativeFactory()
            logger.info("✅ gpiozero: Native factory available")
        except Exception as e:
            logger.warning(f"❌ gpiozero native factory: {e}")
    except ImportError:
        logger.warning("❌ gpiozero: Not available")
    
    # Test pigpio
    try:
        import pigpio
        logger.info("✅ pigpio: Import successful")
    except ImportError:
        logger.warning("❌ pigpio: Not available")

def check_container_environment():
    """Check container-specific environment"""
    logger.info("=== Container Environment ===")
    
    # Check if we're in a container
    if os.path.exists("/.dockerenv"):
        logger.info("✅ Running in Docker container")
    
    # Check cgroup information
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup_info = f.read()
            if "docker" in cgroup_info or "container" in cgroup_info:
                logger.info("✅ Container detected via cgroup")
    except:
        pass
    
    # Check mounted devices
    rc, stdout, stderr = run_command("mount | grep '/dev'")
    if rc == 0:
        logger.info("Mounted /dev entries:")
        for line in stdout.strip().split('\n'):
            if line:
                logger.info(f"  {line}")

def test_gpio_hardware():
    """Test actual GPIO hardware with the pins from configuration"""
    logger.info("=== GPIO Hardware Testing ===")
    
    # Get configuration
    button_pin = int(os.getenv('GPIO_PIN', '17'))
    led_red_pin = int(os.getenv('LED_RED_PIN', '22'))
    led_green_pin = int(os.getenv('LED_GREEN_PIN', '23'))
    led_blue_pin = int(os.getenv('LED_BLUE_PIN', '24'))
    
    logger.info(f"Testing with Button:{button_pin}, LEDs R:{led_red_pin} G:{led_green_pin} B:{led_blue_pin}")
    
    # Test with lgpio first
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        
        # Test button pin
        try:
            lgpio.gpio_claim_input(chip, button_pin, lgpio.SET_PULL_UP)
            value = lgpio.gpio_read(chip, button_pin)
            logger.info(f"✅ Button GPIO {button_pin}: {value} ({'PRESSED' if value == 0 else 'RELEASED'})")
            button_ok = True
        except Exception as e:
            logger.error(f"❌ Button GPIO {button_pin}: {e}")
            button_ok = False
        
        # Test LED pins
        led_pins = [led_red_pin, led_green_pin, led_blue_pin]
        led_colors = ['Red', 'Green', 'Blue']
        led_ok = True
        
        for pin, color in zip(led_pins, led_colors):
            try:
                lgpio.gpio_claim_output(chip, pin)
                lgpio.gpio_write(chip, pin, 1)  # Turn on briefly
                lgpio.gpio_write(chip, pin, 0)  # Turn off
                logger.info(f"✅ {color} LED GPIO {pin}: Working")
            except Exception as e:
                logger.error(f"❌ {color} LED GPIO {pin}: {e}")
                led_ok = False
        
        lgpio.gpiochip_close(chip)
        return button_ok, led_ok
        
    except Exception as e:
        logger.error(f"❌ lgpio hardware test failed: {e}")
        
        # Fallback to gpiozero
        try:
            os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
            from gpiozero import Button, LED
            
            # Test button
            try:
                button = Button(button_pin, pull_up=True)
                pressed = button.is_pressed
                logger.info(f"✅ Button GPIO {button_pin}: {'PRESSED' if pressed else 'RELEASED'}")
                button.close()
                button_ok = True
            except Exception as e:
                logger.error(f"❌ Button GPIO {button_pin}: {e}")
                button_ok = False
            
            # Test LEDs
            led_pins = [led_red_pin, led_green_pin, led_blue_pin]
            led_colors = ['Red', 'Green', 'Blue']
            led_ok = True
            
            for pin, color in zip(led_pins, led_colors):
                try:
                    led = LED(pin)
                    led.on()
                    led.off()
                    led.close()
                    logger.info(f"✅ {color} LED GPIO {pin}: Working")
                except Exception as e:
                    logger.error(f"❌ {color} LED GPIO {pin}: {e}")
                    led_ok = False
            
            return button_ok, led_ok
            
        except Exception as e:
            logger.error(f"❌ gpiozero hardware test also failed: {e}")
            return False, False

def main():
    """Run comprehensive diagnostics"""
    logger.info("Starting comprehensive GPIO diagnostics...")
    
    check_device_access()
    check_kernel_modules()
    check_device_permissions()
    test_gpio_libraries()
    check_container_environment()
    
    # Test actual hardware
    button_ok, led_ok = test_gpio_hardware()
    
    logger.info("=" * 50)
    logger.info("DIAGNOSTIC SUMMARY:")
    logger.info(f"Button GPIO: {'✅ WORKING' if button_ok else '❌ FAILED'}")
    logger.info(f"LED GPIOs: {'✅ WORKING' if led_ok else '❌ FAILED'}")
    
    if button_ok and led_ok:
        logger.info("🎉 All GPIO hardware is working!")
    else:
        logger.warning("⚠️ Some GPIO hardware issues detected")
    
    logger.info("Diagnostics complete.")

if __name__ == "__main__":
    main()
