#!/usr/bin/env python3
"""
Enhanced Button Monitor for Wi-Fi Onboarding Add-on
- Improved GPIO handling with multiple fallback methods
- Complete reset functionality
- Container-compatible reset functionality
- Proper debouncing and state management
- Recovery from GPIO errors
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

class ButtonMonitor:
    def __init__(self, gpio_pin=11, hold_time=5, debounce_time=0.05):
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
        """Initialize GPIO with multiple fallback methods"""
        logger.info(f"Initializing GPIO pin {self.gpio_pin} (Pi 5 compatible)")
        
        # Try both the configured pin and GPIO 17 (common button pin)
        pins_to_try = [self.gpio_pin]
        if self.gpio_pin != 17:
            pins_to_try.append(17)
            logger.info(f"Will also try GPIO 17 (physical pin 11) as fallback")
        
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
        """Try GPIO setup using proven working approach from your old code"""
        logger.info(f"Initializing GPIO pin {self.gpio_pin}")

        # Method 1: Try lgpio (RPi 5 and modern systems) - from your old code
        try:
            import lgpio
            chip = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_input(chip, self.gpio_pin, lgpio.SET_PULL_UP)
            
            # Test that we can read the pin  
            test_value = lgpio.gpio_read(chip, self.gpio_pin)
            logger.debug(f"lgpio pin{self.gpio_pin} test read: {test_value}")
            
            self.button_obj = {'chip': chip, 'pin': self.gpio_pin, 'type': 'lgpio_simple'}
            self.gpio_lib = "lgpio"
            logger.info("Using lgpio library")
            return True
        except Exception as e:
            logger.debug(f"lgpio failed: {str(e)}")

        # Method 2: Try gpiozero (recommended for older systems) - from your old code
        try:
            os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
            from gpiozero import Button
            button = Button(self.gpio_pin, pull_up=True, bounce_time=0.1)
            
            # Test that we can read the pin
            test_value = button.is_pressed
            logger.debug(f"gpiozero pin{self.gpio_pin} test read: {test_value}")
            
            self.button_obj = {'button': button, 'type': 'gpiozero_simple'}
            self.gpio_lib = "gpiozero"
            logger.info("Using gpiozero library")
            return True
        except Exception as e:
            logger.debug(f"gpiozero failed: {str(e)}")

        # Method 3: Fallback to file-based button simulation
        logger.info("All GPIO methods failed, using file-based button simulation")
        try:
            button_trigger_file = "/tmp/button_trigger"
            self.button_obj = {'type': 'file_based', 'trigger_file': button_trigger_file}
            self.gpio_lib = "file-based-simulation"
            logger.info(f"Using file-based button simulation - touch {button_trigger_file} to trigger reset")
            return True
        except Exception as e:
            logger.debug(f"File-based button setup failed: {str(e)}")

        logger.error("No working GPIO library found")
        return False

    def setup_sysfs_gpio(self):
        """Setup GPIO using sysfs interface with container-friendly error handling"""
        gpio_base = "/sys/class/gpio"
        gpio_export = f"{gpio_base}/export"
        gpio_dir = f"{gpio_base}/gpio{self.gpio_pin}"
        gpio_direction = f"{gpio_dir}/direction"
        gpio_edge = f"{gpio_dir}/edge"
        
        # Check if we can write to sysfs (container limitation check)
        try:
            # Test write access
            test_result = self.run_command(["test", "-w", gpio_export], log_output=False)
            if test_result and test_result.returncode != 0:
                raise PermissionError("sysfs GPIO export not writable in container")
        except:
            raise PermissionError("sysfs GPIO not accessible in container")
        
        # Export GPIO if not already exported
        if not os.path.exists(gpio_dir):
            try:
                with open(gpio_export, 'w') as f:
                    f.write(str(self.gpio_pin))
                # Wait for the GPIO directory to be created
                for _ in range(10):  # Wait up to 1 second
                    if os.path.exists(gpio_dir):
                        break
                    time.sleep(0.1)
                if not os.path.exists(gpio_dir):
                    raise Exception(f"GPIO directory {gpio_dir} not created after export")
            except (PermissionError, OSError) as e:
                # Container filesystem is read-only for sysfs
                raise Exception(f"Cannot export GPIO {self.gpio_pin} in container: {e}")
        
        # Set direction to input
        try:
            with open(gpio_direction, 'w') as f:
                f.write("in")
        except (PermissionError, OSError) as e:
            raise Exception(f"Cannot set GPIO {self.gpio_pin} direction in container: {e}")
        
        # Set edge detection to none (for polling)
        try:
            if os.path.exists(gpio_edge):
                with open(gpio_edge, 'w') as f:
                    f.write("none")
        except (PermissionError, OSError):
            # Edge setting is optional, continue without it
            logger.debug(f"Could not set edge for GPIO {self.gpio_pin}")
            pass

    def is_button_pressed(self):
        """Check button state using simple approach from your old working code"""
        try:
            if not self.button_obj:
                return False
                
            button_type = self.button_obj.get('type')
            
            if button_type == 'lgpio_simple':
                import lgpio
                chip = self.button_obj['chip']
                pin = self.button_obj['pin']
                return lgpio.gpio_read(chip, pin) == 0  # Active low with pull-up
            
            elif button_type == 'gpiozero_simple':
                return self.button_obj['button'].is_pressed
            
            elif button_type == 'file_based':
                # Check if trigger file exists and remove it
                trigger_file = self.button_obj['trigger_file']
                if os.path.exists(trigger_file):
                    try:
                        os.remove(trigger_file)
                        return True  # Button press detected
                    except:
                        pass
                return False
            
        except Exception as e:
            logger.error(f"Error reading GPIO: {str(e)}")
        
        return False

    def reinitialize_gpio(self):
        """Try to reinitialize GPIO after an error"""
        try:
            self.cleanup_gpio()
            time.sleep(1)
            return self.setup_gpio()
        except Exception as e:
            logger.error(f"GPIO reinitialization failed: {e}")
            return False

    def cleanup_gpio(self):
        """Clean up GPIO resources using simple approach from your old code"""
        try:
            if not self.button_obj:
                return
                
            button_type = self.button_obj.get('type')
            
            if button_type == 'lgpio_simple':
                import lgpio
                chip = self.button_obj['chip']
                lgpio.gpiochip_close(chip)
            
            elif button_type == 'gpiozero_simple':
                self.button_obj['button'].close()
            
            elif button_type == 'file_based':
                # Clean up trigger file if it exists
                try:
                    trigger_file = self.button_obj['trigger_file']
                    if os.path.exists(trigger_file):
                        os.remove(trigger_file)
                except:
                    pass
            
            self.button_obj = None
            
        except Exception as e:
            logger.debug(f"GPIO cleanup error: {str(e)}")

    def debounce_check(self, current_state):
        """Debounce button state changes"""
        current_time = time.time()
        
        # If state changed, update timing
        if current_state != self.is_pressed_state:
            if current_time - self.last_press_time >= self.debounce_time:
                self.is_pressed_state = current_state
                self.last_press_time = current_time
                
                if current_state:  # Button pressed
                    self.press_start_time = current_time
                    logger.debug("Button press detected")
                else:  # Button released
                    press_duration = current_time - self.press_start_time
                    logger.debug(f"Button released after {press_duration:.2f}s")
                
                return True  # State change confirmed
        
        return False  # No state change or still debouncing

    def stop_all_network_services(self):
        """Stop all network services"""
        logger.info("🛑 Stopping all network services...")
        services = [
            "hostapd", "dnsmasq", "wpa_supplicant",
            "dhcpcd", "udhcpc"
        ]
        
        for service in services:
            try:
                self.run_command(["pkill", "-9", "-f", service])
                logger.debug(f"Stopped {service}")
                time.sleep(0.2)
            except Exception as e:
                logger.debug(f"Failed to stop {service}: {str(e)}")

    def reset_wifi_config(self):
        """Completely reset WiFi configuration while preserving ethernet and button monitor"""
        logger.info("🔄 RESET TRIGGERED - Resetting WiFi configuration...")
        
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

        # 5. Signal main process for WiFi reset (don't kill it completely)
        try:
            # Send SIGUSR1 to trigger WiFi reset in main process
            self.run_command(["pkill", "-USR1", "-f", "onboarding.py"])
            logger.info("✅ Signaled main process for WiFi reset")
            time.sleep(3)  # Give it time to process the signal
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
            subprocess.Popen(["hostapd", "/tmp/hostapd.conf"])
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
            ])
            time.sleep(2)
            
            logger.info("✅ Hotspot mode restored on wlan0")
            
        except Exception as e:
            logger.warning(f"Failed to restart hotspot: {e}")

        logger.info("🎉 WiFi reset complete - configuration cleared")
        logger.info("📱 Connect to 'WiFi-Setup' to reconfigure")
        logger.info("🌐 Ethernet connections remain active and accessible")

    def monitor_button_thread(self):
        """Button monitoring using your old working approach"""
        logger.info(f"Monitoring GPIO {self.gpio_pin}, hold for {self.hold_time}s to reset")
        
        hold_counter = 0
        was_pressed = False
        last_file_based_message = 0
        
        try:
            while self.running:
                current_pressed = self.is_button_pressed()
                
                # Special handling for file-based simulation
                if self.button_obj and self.button_obj.get('type') == 'file_based':
                    current_time = time.time()
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
                
                # Hardware button monitoring (from your old code)
                if current_pressed:
                    if not was_pressed:
                        logger.info("Button pressed - starting hold timer")
                        hold_counter = 0
                    
                    hold_counter += 1
                    
                    # Provide feedback at 3 seconds
                    if hold_counter == 3:
                        logger.info("Keep holding for reset...")
                    # Trigger at hold time
                    elif hold_counter >= self.hold_time:
                        logger.info(f"Long press detected ({self.hold_time}s)!")
                        self.reset_wifi_config()
                        break
                else:
                    if was_pressed:
                        logger.info(f"Button released after {hold_counter}s")
                    hold_counter = 0
                
                was_pressed = current_pressed
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Button monitor interrupted")
        except Exception as e:
            logger.error(f"Button monitor error: {str(e)}")
            # Try to recover from error
            if self.reinitialize_gpio():
                logger.info("Recovered from GPIO error, continuing...")
                # Restart monitoring
                self.monitor_button_thread()
        finally:
            self.cleanup_gpio()

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
                    self.monitor_thread = threading.Thread(target=self.monitor_button_thread)
                    self.monitor_thread.daemon = True
                    self.monitor_thread.start()
                
                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Button monitor main loop interrupted")
        finally:
            self.running = False
            self.cleanup_gpio()

    def diagnose_gpio_access(self):
        """Comprehensive GPIO access diagnostics"""
        logger.info("🔍 GPIO Diagnostics Starting...")
        
        # Check device files
        gpio_devices = [
            "/dev/gpiomem",
            "/dev/gpiochip0", 
            "/dev/gpiochip1",
            "/dev/gpiochip2",
            "/dev/gpiochip3", 
            "/dev/gpiochip4",
            "/dev/mem"
        ]
        
        logger.info("📂 Checking GPIO device files:")
        for device in gpio_devices:
            exists = os.path.exists(device)
            if exists:
                try:
                    stat_info = os.stat(device)
                    perms = oct(stat_info.st_mode)[-3:]
                    logger.info(f"  ✅ {device} (permissions: {perms})")
                except:
                    logger.info(f"  ⚠️  {device} (exists but cannot stat)")
            else:
                logger.info(f"  ❌ {device} (missing)")
        
        # Check sysfs GPIO
        logger.info("📁 Checking sysfs GPIO:")
        sysfs_gpio = f"/sys/class/gpio/gpio{self.gpio_pin}"
        if os.path.exists("/sys/class/gpio"):
            logger.info("  ✅ /sys/class/gpio exists")
            try:
                gpio_list = os.listdir("/sys/class/gpio")
                logger.info(f"  📋 Available GPIO entries: {gpio_list}")
            except Exception as e:
                logger.info(f"  ⚠️  Cannot list /sys/class/gpio: {e}")
        else:
            logger.info("  ❌ /sys/class/gpio missing")
        
        # Test GPIO library imports
        logger.info("📚 Testing GPIO library imports:")
        
        # Test rpi-lgpio (RPi.GPIO replacement)
        try:
            import RPi.GPIO as GPIO
            logger.info("  ✅ rpi-lgpio (RPi.GPIO replacement) imported successfully")
            try:
                # Test basic setup
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                state = GPIO.input(self.gpio_pin)
                GPIO.cleanup()
                logger.info(f"    ✅ rpi-lgpio GPIO test successful (pin {self.gpio_pin} = {state})")
            except Exception as e:
                logger.info(f"    ❌ rpi-lgpio GPIO test failed: {e}")
                try:
                    GPIO.cleanup()
                except:
                    pass
        except ImportError:
            logger.info("  ❌ rpi-lgpio not available")
        except Exception as e:
            logger.info(f"  ⚠️  rpi-lgpio error: {e}")
        
        # Test gpiozero with different pin factories
        pin_factories = ['lgpio', 'native']
        for factory in pin_factories:
            try:
                os.environ['GPIOZERO_PIN_FACTORY'] = factory
                from gpiozero import Button
                button = Button(self.gpio_pin, pull_up=True)
                state = button.is_pressed
                button.close()
                logger.info(f"  ✅ gpiozero with {factory} factory successful (pressed: {state})")
                break  # Stop after first successful test
            except ImportError:
                logger.info(f"  ❌ gpiozero with {factory} factory not available")
            except Exception as e:
                logger.info(f"  ❌ gpiozero with {factory} factory failed: {e}")
        
        # Test python-periphery
        try:
            from periphery import GPIO as PeripheryGPIO
            gpio_pin = PeripheryGPIO(f"/dev/gpiochip4", self.gpio_pin, "in")
            gpio_pin.bias = "pull_up"
            state = gpio_pin.read()
            gpio_pin.close()
            logger.info(f"  ✅ python-periphery successful (pin {self.gpio_pin} = {state})")
        except ImportError:
            logger.info("  ❌ python-periphery not available")
        except Exception as e:
            logger.info(f"  ❌ python-periphery failed: {e}")
        
        # Check running processes that might interfere
        logger.info("🔄 Checking for interfering processes:")
        try:
            result = self.run_command(["ps", "aux"])
            if result and result.returncode == 0:
                lines = result.stdout.split('\n')
                gpio_processes = [line for line in lines if 'gpio' in line.lower() and 'button_monitor' not in line]
                if gpio_processes:
                    logger.info("  ⚠️  Found GPIO-related processes:")
                    for proc in gpio_processes:
                        logger.info(f"    {proc}")
                else:
                    logger.info("  ✅ No interfering GPIO processes found")
        except Exception as e:
            logger.info(f"  ⚠️  Cannot check processes: {e}")
        
        # Check kernel version and platform
        logger.info("🖥️  System information:")
        try:
            with open("/proc/version", "r") as f:
                kernel_info = f.read().strip()
                logger.info(f"  📦 Kernel: {kernel_info}")
        except:
            pass
        
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().strip().replace('\x00', '')
                logger.info(f"  🔧 Hardware: {model}")
        except:
            logger.info("  🔧 Hardware: Unknown")
        
        logger.info("🔍 GPIO Diagnostics Complete")

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
    parser.add_argument('--pin', type=int, default=11, help='GPIO pin number (default: 11)')
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
            
            # Test reading for 10 seconds
            logger.info("Testing button reading for 10 seconds...")
            for test_cycle in range(10):
                pressed = monitor.is_button_pressed()
                logger.info(f"Button state: {'PRESSED' if pressed else 'RELEASED'}")
                time.sleep(1)
            
            monitor.cleanup_gpio()
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
