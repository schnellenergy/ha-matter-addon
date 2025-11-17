#!/usr/bin/env python3
"""
Enhanced Button Monitor for Wi-Fi Onboarding Add-on
- Improved GPIO handling with multiple fallback methods
- Complete reset functionality
- Container-compatible reset functionality
- Proper debouncing and state management
- Recovery from GPIO errors
- LED status integration
"""

import time
import subprocess
import sys
import os
import json
import signal
import logging
import threading
from pathlib import Path
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def set_led_status(status: str):
    """Helper function to control the LED by writing to a status file."""
    try:
        with open("/tmp/led_status", 'w') as f:
            f.write(status)
        logger.info(f"🚥 LED status set to: {status}")
    except Exception as e:
        logger.error(f"Failed to write LED status: {e}")

class ButtonMonitor:
    def __init__(self, gpio_pin=17, hold_time=5, debounce_time=0.05):
        self.gpio_pin = gpio_pin
        self.hold_time = hold_time
        self.debounce_time = debounce_time
        self.running = True
        self.button_obj = None
        self.gpio_lib = None
        self.reset_flag = "/tmp/wifi_reset"
        self.config_file = "/data/wifi_config.json"
        self.state_file = "/tmp/wifi_state.json"
        self.last_press_time = 0
        self.press_start_time = 0
        self.is_pressed_state = False
        self.monitor_thread = None

    def run_command(self, cmd, timeout=10):
        """Run shell command safely"""
        try:
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            return None
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return None

    def setup_gpio(self):
        """Initialize GPIO with multiple fallback methods using proven working approach"""
        logger.info(f"Initializing GPIO pin {self.gpio_pin} (Pi 5 compatible)")
        
        # Try both the configured pin and common button pins as fallback
        pins_to_try = [self.gpio_pin]
        if self.gpio_pin != 17:
            pins_to_try.append(17)
        if self.gpio_pin != 11:
            pins_to_try.append(11)
            
        original_pin = self.gpio_pin
        
        for pin_to_try in pins_to_try:
            self.gpio_pin = pin_to_try
            logger.debug(f"Trying GPIO pin {pin_to_try}")
            
            if self._try_gpio_setup():
                if pin_to_try != original_pin:
                    logger.info(f"✅ Button found on GPIO {pin_to_try} (not GPIO {original_pin})")
                return True
        
        # Restore original pin if all failed
        self.gpio_pin = original_pin
        logger.error("No working GPIO library found")
        return False
    
    def _try_gpio_setup(self):
        """Try GPIO setup using EXACT same approach as working LED/GPIO tests"""
        logger.info(f"🔘 BUTTON SETUP: Using same approach as working LED tests")
        logger.info(f"Initializing GPIO pin {self.gpio_pin}")
        
        # Debug information
        import sys
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Python version: {sys.version}")

        # Method 1: Use EXACT same lgpio approach as working LED tests
        try:
            import lgpio
            logger.info("✅ lgpio import successful")
            
            # Try multiple gpiochips (RPi 5 exposes different chips)
            chips_to_try = [0, 4, 10, 11, 12, 13]
            last_err = None
            for chip_num in chips_to_try:
                try:
                    chip = lgpio.gpiochip_open(chip_num)
                    logger.info(f"✅ lgpio GPIO chip {chip_num} opened")
                    
                    # Handle GPIO busy error (common issue on Pi)
                    try:
                        lgpio.gpio_claim_input(chip, self.gpio_pin, lgpio.SET_PULL_UP)
                        logger.info(f"✅ GPIO {self.gpio_pin} claimed as input with pull-up on chip {chip_num}")
                    except lgpio.error as e:
                        if "GPIO busy" in str(e):
                            logger.warning(f"⚠️  GPIO {self.gpio_pin} busy - trying to free it first...")
                            try:
                                lgpio.gpio_free(chip, self.gpio_pin)
                                logger.info(f"✅ GPIO {self.gpio_pin} freed from previous claim on chip {chip_num}")
                                time.sleep(0.5)
                                lgpio.gpio_claim_input(chip, self.gpio_pin, lgpio.SET_PULL_UP)
                                logger.info(f"✅ GPIO {self.gpio_pin} successfully reclaimed on chip {chip_num}")
                            except Exception as free_error:
                                logger.error(f"❌ Failed to free/reclaim GPIO {self.gpio_pin} on chip {chip_num}: {free_error}")
                                lgpio.gpiochip_close(chip)
                                last_err = e
                                continue
                        else:
                            logger.error(f"❌ GPIO claim error on chip {chip_num}: {e}")
                            lgpio.gpiochip_close(chip)
                            last_err = e
                            continue
                    
                    # Test that we can read the pin (same as LED test approach)
                    test_value = lgpio.gpio_read(chip, self.gpio_pin)
                    logger.info(f"✅ GPIO {self.gpio_pin} test read on chip {chip_num}: {test_value} ({'PRESSED' if test_value == 0 else 'RELEASED'})")
                    
                    self.button_obj = {'chip': chip, 'pin': self.gpio_pin, 'type': 'lgpio_simple', 'chip_num': chip_num}
                    self.gpio_lib = "lgpio"
                    logger.info("🎉 SUCCESS: Button using lgpio (same as working LEDs)")
                    return True
                except Exception as e:
                    last_err = e
                    logger.debug(f"lgpio chip {chip_num} failed: {e}")
                    try:
                        # Ensure chip is closed if opened
                        if 'chip' in locals():
                            lgpio.gpiochip_close(chip)
                    except Exception:
                        pass
                    continue
            
            if last_err:
                raise last_err
            
        except ImportError as e:
            logger.error(f"❌ lgpio import failed: {str(e)}")
            logger.error("   This means GPIO libraries not available in current Python environment")
        except Exception as e:
            logger.error(f"❌ lgpio hardware access failed: {str(e)}")

        # Method 2: Try gpiozero with same pin factory as LED tests
        try:
            import os
            os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
            from gpiozero import Button
            logger.info("✅ gpiozero import successful")
            
            button = Button(self.gpio_pin, pull_up=True, bounce_time=0.1)
            logger.info(f"✅ gpiozero Button({self.gpio_pin}) created")
            
            # Test that we can read the pin
            test_value = button.is_pressed
            logger.info(f"✅ gpiozero pin {self.gpio_pin} test read: {test_value}")
            
            self.button_obj = {'button': button, 'type': 'gpiozero_simple'}
            self.gpio_lib = "gpiozero"
            logger.info("🎉 SUCCESS: Button using gpiozero")
            return True
            
        except ImportError as e:
            logger.error(f"❌ gpiozero import failed: {str(e)}")
        except Exception as e:
            logger.error(f"❌ gpiozero hardware access failed: {str(e)}")

        # Method 3: File-based fallback
        logger.warning("⚠️  HARDWARE GPIO FAILED - All methods failed")
        logger.warning("⚠️  This shouldn't happen if LEDs are working with same libraries")
        logger.info("💡 Check if button monitor is using same Python environment as LED controller")
        
        try:
            button_trigger_file = "/tmp/button_trigger"
            self.button_obj = {'type': 'file_based', 'trigger_file': button_trigger_file}
            self.gpio_lib = "file-based-simulation"
            logger.info(f"✅ File-based button simulation ready")
            logger.info(f"📁 Trigger: touch {button_trigger_file}")
            return True
        except Exception as e:
            logger.error(f"❌ File-based button setup failed: {str(e)}")

        logger.error("❌ NO WORKING GPIO METHODS FOUND")
        return False

    def is_button_pressed(self):
        """Check button state with explicit debugging"""
        try:
            if not self.button_obj:
                return False

            button_type = self.button_obj.get('type')

            if button_type == 'lgpio_simple':
                import lgpio
                chip = self.button_obj['chip']
                pin = self.button_obj['pin']
                value = lgpio.gpio_read(chip, pin)
                # Active low with pull-up: 0 = pressed, 1 = released
                pressed = (value == 0)
                return pressed

            elif button_type == 'gpiozero_simple':
                pressed = self.button_obj['button'].is_pressed
                return pressed

            elif button_type == 'file_based':
                # Check if trigger file exists and remove it
                trigger_file = self.button_obj['trigger_file']
                if os.path.exists(trigger_file):
                    try:
                        os.remove(trigger_file)
                        logger.info("📁 File-based button trigger detected and removed")
                        return True  # Button press detected
                    except Exception as e:
                        logger.debug(f"Failed to remove trigger file: {e}")
                        pass
                return False

        except Exception as e:
            logger.error(f"🔘 Error reading GPIO button: {str(e)}")

        return False

    def cleanup_gpio(self):
        """Clean up GPIO resources using simple approach from reference code"""
        try:
            if not self.button_obj:
                return

            button_type = self.button_obj.get('type')

            if button_type == 'lgpio_simple':
                import lgpio
                chip = self.button_obj['chip']
                lgpio.gpiochip_close(chip)
                logger.debug("✅ lgpio cleanup completed")

            elif button_type == 'gpiozero_simple':
                self.button_obj['button'].close()
                logger.debug("✅ gpiozero cleanup completed")

            elif button_type == 'rpi_gpio':
                GPIO = self.button_obj['gpio']
                GPIO.cleanup()
                logger.debug("✅ RPi.GPIO cleanup completed")

            elif button_type == 'file_based':
                # Clean up trigger file if it exists
                try:
                    trigger_file = self.button_obj['trigger_file']
                    if os.path.exists(trigger_file):
                        os.remove(trigger_file)
                    logger.debug("✅ File-based cleanup completed")
                except:
                    pass

            self.button_obj = None

        except Exception as e:
            logger.debug(f"GPIO cleanup error: {str(e)}")

    def monitor_button_thread(self):
        """Button monitoring with explicit logging to track button presses"""
        logger.info(f"🔘 BUTTON MONITORING: GPIO {self.gpio_pin}, hold for {self.hold_time}s to reset")
        logger.info(f"🔘 BUTTON TYPE: {self.button_obj.get('type') if self.button_obj else 'None'}")
        
        hold_counter = 0
        was_pressed = False
        last_file_based_message = 0
        
        # Add explicit button state logging every 10 seconds for hardware debugging
        last_status_log = 0
        
        try:
            while self.running:
                current_pressed = self.is_button_pressed()
                current_time = time.time()
                
                # Log button state every 10 seconds for debugging
                if current_time - last_status_log > 10:
                    button_type = self.button_obj.get('type') if self.button_obj else 'None'
                    logger.info(f"🔘 STATUS: Button type={button_type}, state={'PRESSED' if current_pressed else 'RELEASED'}")
                    last_status_log = current_time
                
                # Special handling for file-based simulation
                if self.button_obj and self.button_obj.get('type') == 'file_based':
                    # Show reminder every 5 minutes for file-based simulation
                    if current_time - last_file_based_message > 300:  # 5 minutes
                        trigger_file = self.button_obj['trigger_file']
                        logger.info(f"📁 File-based button active - run 'touch {trigger_file}' to trigger reset")
                        last_file_based_message = current_time
                    
                    if current_pressed:
                        logger.info("🚨 FILE-BASED RESET TRIGGERED!")
                        self.reset_wifi_config()
                        break
                    
                    time.sleep(1)
                    continue
                
                # Hardware button monitoring with explicit state change logging
                if current_pressed:
                    if not was_pressed:
                        logger.info(f"🔘 BUTTON PRESSED: GPIO {self.gpio_pin} - starting hold timer")
                        hold_counter = 0
                    
                    hold_counter += 1
                    
                    # Provide feedback during hold
                    if hold_counter == 1:
                        logger.info(f"🔘 HOLD TIMER: 1/{self.hold_time}s - keep holding...")
                    elif hold_counter == 3:
                        logger.info(f"🔘 HOLD TIMER: 3/{self.hold_time}s - keep holding for reset...")
                    elif hold_counter == self.hold_time - 1:
                        logger.info(f"🔘 HOLD TIMER: {hold_counter}/{self.hold_time}s - almost there...")
                    
                    # Trigger at hold time
                    if hold_counter >= self.hold_time:
                        logger.info(f"🚨 FACTORY RESET: Long press detected ({self.hold_time}s)!")
                        self.reset_wifi_config()
                        break
                else:
                    if was_pressed:
                        logger.info(f"🔘 BUTTON RELEASED: GPIO {self.gpio_pin} after {hold_counter}s")
                        if hold_counter < self.hold_time:
                            logger.info(f"🔘 SHORT PRESS: {hold_counter}s < {self.hold_time}s - no reset")
                    hold_counter = 0
                
                was_pressed = current_pressed
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🔘 Button monitor interrupted")
        except Exception as e:
            logger.error(f"🔘 Button monitor error: {str(e)}")
            # Try to recover from error
            if self.reinitialize_gpio():
                logger.info("🔘 Recovered from GPIO error, continuing...")
                # Restart monitoring
                self.monitor_button_thread()
        finally:
            self.cleanup_gpio()

    def reinitialize_gpio(self):
        """Try to reinitialize GPIO after an error"""
        try:
            self.cleanup_gpio()
            time.sleep(1)
            return self.setup_gpio()
        except Exception as e:
            logger.error(f"GPIO reinitialization failed: {e}")
            return False

    def reset_wifi_config(self):
        """Completely reset WiFi configuration while preserving ethernet and button monitor"""
        logger.info("🚨 RESET TRIGGERED - Resetting WiFi configuration...")
        
        # Immediate LED feedback
        try:
            set_led_status('factory_reset')  # Blinking red to indicate reset in progress
        except Exception:
            pass
        
        # 1. Stop WiFi-related services only (preserve ethernet and button monitor)
        logger.info("🛑 Stopping WiFi services only...")
        wifi_services = [
            "wpa_supplicant", "dhcpcd", "udhcpc"
        ]
        
        for service in wifi_services:
            try:
                self.run_command(["pkill", "-9", "-f", service])
                logger.debug(f"Stopped {service}")
                time.sleep(0.2)
            except Exception as e:
                logger.debug(f"Failed to stop {service}: {str(e)}")
        
        # 2. Reset wlan0 interface only (preserve ethernet interfaces)
        try:
            logger.info("🔄 Resetting wlan0 interface...")
            self.run_command(["ip", "link", "set", "wlan0", "down"], timeout=10)
            time.sleep(1)
            self.run_command(["ip", "addr", "flush", "dev", "wlan0"], timeout=10)
            time.sleep(1)
            # Only flush wlan0 routes, not all routes
            self.run_command(["sh", "-c", "ip route | grep wlan0 | while read route; do ip route del $route; done"], timeout=10)
            time.sleep(1)
            self.run_command(["ip", "link", "set", "wlan0", "up"], timeout=10)
            time.sleep(2)
            logger.info("✅ wlan0 interface reset (ethernet preserved)")
        except Exception as e:
            logger.warning(f"Failed to reset wlan0: {e}")
        
        # 3. Remove WiFi configuration files only
        config_files = [
            self.config_file,
            self.state_file,
            "/tmp/wifi_onboarding.lock",
            "/tmp/wpa_supplicant.conf"
        ]
        
        for file_path in config_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Removed {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove {file_path}: {str(e)}")

        # 4. Create reset flag for main process
        try:
            Path(self.reset_flag).touch()
            logger.info(f"✅ Created reset flag at {self.reset_flag}")
        except Exception as e:
            logger.error(f"Failed to create reset flag: {str(e)}")

        # 5. Signal main process for factory reset (don't kill it completely)
        try:
            # Prefer factory reset signal (SIGUSR2) to improved_ble_service.py
            self.run_command(["pkill", "-USR2", "-f", "improved_ble_service.py"])
            logger.info("✅ Signaled main process for FACTORY RESET (SIGUSR2)")
            time.sleep(1)
            # Fallback: also send WiFi reset signal (SIGUSR1)
            self.run_command(["pkill", "-USR1", "-f", "improved_ble_service.py"])
            logger.info("ℹ️ Also signaled WiFi reset (SIGUSR1) as fallback")
            time.sleep(2)  # Give it time to process the signals
        except Exception as e:
            logger.warning(f"Failed to signal main process: {e}")

        # 6. Restart hotspot mode for wlan0 (keep ethernet untouched)
        try:
            logger.info("🏗️ Restarting hotspot mode on wlan0...")
            
            # Set up wlan0 for hotspot
            self.run_command(["ip", "addr", "add", "192.168.4.1/24", "dev", "wlan0"])
            time.sleep(1)
            
            # Create hostapd config
            hostapd_config = """interface=wlan0
driver=nl80211
ssid=WiFi-Setup
hw_mode=g
channel=6
auth_algs=1
wpa=0
"""
            with open('/tmp/hostapd.conf', 'w') as f:
                f.write(hostapd_config)
            
            # Stop any existing hostapd/dnsmasq and restart
            self.run_command(["pkill", "-9", "hostapd"])
            self.run_command(["pkill", "-9", "dnsmasq"])
            time.sleep(2)
            
            # Start hostapd in background
            subprocess.Popen(["hostapd", "/tmp/hostapd.conf"])  # nosec - executed in controlled environment
            time.sleep(3)
            
            # Start dnsmasq
            subprocess.Popen([
                "dnsmasq",
                "--interface=wlan0",
                "--dhcp-range=192.168.4.10,192.168.4.50,12h",
                "--dhcp-option=3,192.168.4.1",
                "--dhcp-option=6,192.168.4.1",
                "--server=8.8.8.8",
                "--address=/#/192.168.4.1",
                "--no-resolv",
                "--no-hosts",
                "--log-dhcp"
            ])  # nosec - executed in controlled environment
            time.sleep(2)
            
            logger.info("✅ Hotspot mode restored on wlan0")
            
        except Exception as e:
            logger.warning(f"Failed to restart hotspot: {e}")

        logger.info("🎉 WiFi reset complete - configuration cleared")
        logger.info("📱 Connect to 'WiFi-Setup' to reconfigure")
        logger.info("🌐 Ethernet connections remain active and accessible")

    def monitor_button(self):
        """Main button monitoring loop with threading"""
        if not self.setup_gpio():
            logger.error("❌ Button monitoring FAILED - GPIO initialization failed")
            logger.info("Running GPIO diagnostics to identify the problem...")
            self.diagnose_gpio_access()
            
            # Don't exit - the file-based fallback should be available
            if not self.button_obj or self.button_obj.get('type') != 'file_based':
                logger.error("Button monitor exiting due to GPIO failure")
                sys.exit(1)
            else:
                logger.info("Continuing with file-based button simulation")

        logger.info(f"🎛️  Monitoring GPIO {self.gpio_pin}, hold for {self.hold_time}s to reset")
        
        # Start monitoring in thread
        self.monitor_thread = threading.Thread(target=self.monitor_button_thread)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        # Keep main thread alive
        try:
            while self.running:
                # Check if monitoring thread is still alive
                if not self.monitor_thread.is_alive():
                    logger.warning("Button monitoring thread died, restarting...")
                    # Reinitialize GPIO before restarting thread
                    if not self.setup_gpio():
                        logger.error("Failed to reinitialize GPIO, retrying in 10 seconds...")
                        time.sleep(10)
                        continue
                    self.monitor_thread = threading.Thread(target=self.monitor_button_thread)
                    self.monitor_thread.daemon = True
                    self.monitor_thread.start()
                
                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Button monitor main loop interrupted")
        finally:
            self.running = False
            self.cleanup_gpio()

    def stop(self):
        """Stop button monitoring"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        self.cleanup_gpio()

    def diagnose_gpio_access(self):
        """Diagnostic information for GPIO troubleshooting - Raspberry Pi 5 compatible"""
        logger.info("=== RASPBERRY PI 5 GPIO DIAGNOSTICS ===")
        
        # Check for Raspberry Pi model
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                logger.info(f"🖥️ Detected device: {model}")
                if "Raspberry Pi 5" in model:
                    logger.info("✅ Raspberry Pi 5 detected - using RPi 5 specific GPIO chip detection")
        except Exception as e:
            logger.info(f"ℹ️ Could not detect Pi model: {e}")
        
        # Check for GPIO devices - RPi 5 specific
        gpio_devices = [
            "/dev/gpiomem", 
            "/dev/gpiochip0",   # Legacy
            "/dev/gpiochip4",   # RPi 5
            "/dev/gpiochip10",  # RPi 5  
            "/dev/gpiochip11",  # RPi 5
            "/dev/gpiochip12",  # RPi 5
            "/dev/gpiochip13",  # RPi 5
            "/dev/mem"
        ]
        
        for device in gpio_devices:
            if os.path.exists(device):
                try:
                    stat = os.stat(device)
                    logger.info(f"✅ {device} exists (permissions: {oct(stat.st_mode)})")
                except Exception as e:
                    logger.info(f"❌ {device} exists but stat failed: {e}")
            else:
                logger.info(f"❌ {device} not found")
        
        # Check GPIO chip information - RPi 5 specific
        logger.info("🔍 Checking GPIO chips for RPi 5...")
        chips_found = []
        for chip_num in [0, 4, 10, 11, 12, 13]:
            chip_path = f"/dev/gpiochip{chip_num}"
            if os.path.exists(chip_path):
                chips_found.append(chip_num)
                logger.info(f"✅ GPIO chip {chip_num} available")
                
                # Try to test GPIO 17 on this chip if lgpio is available
                try:
                    import lgpio
                    chip = lgpio.gpiochip_open(chip_num)
                    try:
                        lgpio.gpio_claim_input(chip, 17, lgpio.SET_PULL_UP)
                        test_value = lgpio.gpio_read(chip, 17)
                        logger.info(f"   🔧 GPIO 17 on chip {chip_num}: {test_value} (0=pressed, 1=released)")
                        lgpio.gpio_free(chip, 17)
                    except Exception as e:
                        logger.info(f"   ❌ GPIO 17 not available on chip {chip_num}: {e}")
                    lgpio.gpiochip_close(chip)
                except ImportError:
                    logger.info(f"   ❌ lgpio not available to test chip {chip_num}")
                except Exception as e:
                    logger.info(f"   ❌ Failed to test chip {chip_num}: {e}")
        
        if chips_found:
            logger.info(f"📊 Summary: Found {len(chips_found)} GPIO chips: {chips_found}")
        else:
            logger.error("❌ No GPIO chips found! This may indicate a permission or kernel issue.")
        
        # Check for library installations
        libraries = [
            ("lgpio", "import lgpio", "Raspberry Pi 5 preferred"),
            ("gpiozero", "import gpiozero", "Universal GPIO library"), 
            ("RPi.GPIO", "import RPi.GPIO", "Legacy GPIO library")
        ]
        
        logger.info("📚 GPIO Library availability:")
        for lib_name, import_cmd, description in libraries:
            try:
                exec(import_cmd)
                logger.info(f"✅ {lib_name} library available ({description})")
            except ImportError:
                logger.info(f"❌ {lib_name} library not available ({description})")
        
        logger.info("=== END RPi 5 GPIO DIAGNOSTICS ===")

    def get_system_info(self):
        """Get system information for debugging"""
        info = {
            "gpio_pin": self.gpio_pin,
            "hold_time": self.hold_time,
            "gpio_lib": self.gpio_lib,
            "config_exists": os.path.exists(self.config_file),
            "reset_flag_exists": os.path.exists(self.reset_flag)
        }
        
        try:
            # Check if GPIO is available
            info["gpio_available"] = os.path.exists(f"/sys/class/gpio/gpio{self.gpio_pin}")
        except:
            info["gpio_available"] = False
        
        # Check wlan0 status
        try:
            result = self.run_command(["ip", "addr", "show", "wlan0"])
            info["wlan0_status"] = result.stdout if result and result.returncode == 0 else "not found"
        except:
            info["wlan0_status"] = "error"
        
        return info

def main():
    """Entry point with signal handling and enhanced error recovery"""
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='WiFi Onboarding Button Monitor')
    parser.add_argument('--pin', type=int, default=17, help='GPIO pin number (default: 17)')
    parser.add_argument('--hold', type=int, default=5, help='Hold time in seconds (default: 5)')
    parser.add_argument('--debounce', type=float, default=0.05, help='Debounce time in seconds (default: 0.05)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--test', action='store_true', help='Test GPIO and exit')
    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create monitor instance
    monitor = ButtonMonitor(
        gpio_pin=args.pin,
        hold_time=args.hold,
        debounce_time=args.debounce
    )

    # Test mode
    if args.test:
        logger.info("Testing GPIO setup...")
        monitor.diagnose_gpio_access()
        
        if monitor.setup_gpio():
            logger.info("✅ GPIO setup successful")
            logger.info(f"System info: {monitor.get_system_info()}")
            
            # Quick test - just 2 seconds instead of 10
            logger.info("Testing button reading for 2 seconds...")
            for test_cycle in range(2):
                pressed = monitor.is_button_pressed()
                logger.info(f"Button state: {'PRESSED' if pressed else 'RELEASED'}")
                time.sleep(1)
            
            monitor.cleanup_gpio()
            logger.info("✅ Button test completed")
        else:
            logger.error("❌ GPIO setup failed")
            logger.error("See diagnostics above for details")
            sys.exit(1)
        return

    # Setup signal handlers
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        monitor.running = False
    
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Log startup info
    logger.info("🚀 Starting Button Monitor for WiFi Reset")
    logger.info(f"System info: {monitor.get_system_info()}")

    # Start monitoring with retry logic
    max_restarts = 3
    restart_count = 0
    
    while restart_count < max_restarts and monitor.running:
        try:
            monitor.monitor_button()
            break  # Normal exit
        except Exception as e:
            restart_count += 1
            logger.error(f"Button monitor crashed: {e}")
            
            if restart_count < max_restarts:
                logger.info(f"Restarting button monitor ({restart_count}/{max_restarts})...")
                time.sleep(5)  # Brief delay before restart
                monitor.cleanup_gpio()  # Clean up before retry
            else:
                logger.error("Maximum restart attempts reached, giving up")
                break

    logger.info("Button monitor shutdown complete")

if __name__ == "__main__":
    main()
