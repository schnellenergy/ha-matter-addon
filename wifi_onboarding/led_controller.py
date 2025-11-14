#!/usr/bin/env python3
"""
Simplified LED Status Controller for SMASH Hub
This version is controlled externally by writing a status to /tmp/led_status
"""

import time
import threading
import logging
import os
import json

logger = logging.getLogger(__name__)

class LEDController:
    def __init__(self, red_pin=None, green_pin=None, blue_pin=None):
        self.red_pin = red_pin or int(os.getenv("LED_RED_PIN", "22"))
        self.green_pin = green_pin or int(os.getenv("LED_GREEN_PIN", "23"))
        self.blue_pin = blue_pin or int(os.getenv("LED_BLUE_PIN", "24"))
        
        self.led_pins = {'red': self.red_pin, 'green': self.green_pin, 'blue': self.blue_pin}
        self.gpio_lib = None
        self.gpio_objects = {}
        
        self.led_enabled = os.getenv("ENABLE_LED", "true").lower() == "true"
        if not self.led_enabled:
            logger.info("🚥 LED functionality disabled via configuration")
        
        self.current_status = "booting"
        self.running = True
        self.blink_thread = None
        self.blink_state = False
        self.status_file = "/tmp/led_status"

        # LED status patterns based on exact project requirements
        self.status_patterns = {
            'booting': {'red': 'blink', 'green': 'off', 'blue': 'off'},          # Boot: Blinking red until connection
            'error': {'red': 'blink', 'green': 'off', 'blue': 'off'},           # Error: Blinking red
            'factory_reset': {'red': 'blink', 'green': 'off', 'blue': 'off'},   # Reset: Blinking red
            
            # Network connected states (highest priority to lowest)
            'ethernet_connected': {'red': 'off', 'green': 'solid', 'blue': 'off'},  # Ethernet: Solid green (highest priority)
            'wifi_connected': {'red': 'off', 'green': 'off', 'blue': 'solid'},      # WiFi only: Solid blue
            
            # Transitional/connecting states
            'wifi_connecting': {'red': 'solid', 'green': 'off', 'blue': 'off'},    # WiFi connecting: Solid red (reconnection)
            'ble_advertising': {'red': 'blink', 'green': 'off', 'blue': 'off'},     # BLE ready: Blinking red (fresh setup)
            
            # Special states
            'setup_in_progress': {'red': 'blink', 'green': 'off', 'blue': 'blink'}, # Setup: Red+Blue blink
            'wifi_no_internet': {'red': 'off', 'green': 'off', 'blue': 'blink'},    # WiFi but no internet: Blinking blue
            'ethernet_no_internet': {'red': 'off', 'green': 'blink', 'blue': 'off'}, # Ethernet but no internet: Blinking green
            'internet_connected': {'red': 'off', 'green': 'off', 'blue': 'solid'},  # WiFi with internet: Solid blue
            'dual_network': {'red': 'off', 'green': 'solid', 'blue': 'off'},       # Both networks: Ethernet priority (solid green)
            'shutdown': {'red': 'off', 'green': 'off', 'blue': 'off'},             # Shutdown: All off
        }
        
    def setup_gpio(self) -> bool:
        if not self.led_enabled:
            logger.info("🚥 LED setup skipped - disabled")
            return True
            
        logger.info(f"🚥 Initializing LED GPIOs: R={self.red_pin}, G={self.green_pin}, B={self.blue_pin}")
        
        # Try lgpio first (for RPi 5) with multiple chip support
        try:
            import lgpio
            chips_to_try = [0, 4, 10, 11, 12, 13] # Added 4 for RPi5, more chips for compatibility
            for chip_num in chips_to_try:
                try:
                    chip = lgpio.gpiochip_open(chip_num)
                    # Test setup all LEDs at once
                    for color, pin in self.led_pins.items():
                        lgpio.gpio_claim_output(chip, pin)
                        lgpio.gpio_write(chip, pin, 0)  # Start with LEDs off
                        self.gpio_objects[color] = {'chip': chip, 'pin': pin, 'chip_num': chip_num}
                    self.gpio_lib = "lgpio"
                    logger.info(f"✅ LED GPIO initialized using lgpio on gpiochip{chip_num}")
                    return True
                except Exception as e:
                    logger.debug(f"lgpio gpiochip{chip_num} failed: {e}")
                    continue
        except ImportError:
            logger.debug("lgpio not available")

        # Fallback to gpiozero (from reference implementation)
        try:
            from gpiozero import LED
            # Force native pin factory for container compatibility
            import os
            os.environ['GPIOZERO_PIN_FACTORY'] = 'native'
            
            for color, pin in self.led_pins.items():
                led = LED(pin)
                led.off()  # Start with LED off
                self.gpio_objects[color] = {'led': led, 'pin': pin}
            self.gpio_lib = "gpiozero"
            logger.info("✅ LED GPIO initialized using gpiozero")
            return True
        except Exception as e:
            logger.debug(f"gpiozero failed: {e}")

        # Final fallback - just log the status (for debugging without hardware)
        logger.warning("❌ All LED GPIO methods failed - LED control disabled")
        logger.info("LEDs will be simulated via log messages only")
        self.gpio_lib = "simulation"
        for color, pin in self.led_pins.items():
            self.gpio_objects[color] = {'simulation': True, 'pin': pin}
        return True  # Don't fail completely

    def set_led(self, color: str, state: bool):
        if not self.led_enabled or color not in self.gpio_objects:
            return
            
        try:
            if self.gpio_lib == "lgpio":
                import lgpio
                gpio_obj = self.gpio_objects[color]
                lgpio.gpio_write(gpio_obj['chip'], gpio_obj['pin'], 1 if state else 0)
            elif self.gpio_lib == "gpiozero":
                led = self.gpio_objects[color]['led']
                if state: 
                    led.on()
                else: 
                    led.off()
            elif self.gpio_lib == "simulation":
                # Log simulation for debugging
                pin = self.gpio_objects[color]['pin']
                state_str = "ON" if state else "OFF"
                logger.debug(f"🚥 LED {color.upper()} (GPIO {pin}): {state_str}")
        except Exception as e:
            logger.error(f"❌ Failed to set {color} LED: {e}")
            logger.error(f"❌ Error setting {color} LED: {e}")

    def _apply_status_pattern(self, status: str):
        if status not in self.status_patterns:
            logger.warning(f"⚠️ Unknown status pattern: {status}")
            return
        
        pattern = self.status_patterns[status]
        logger.info(f"🚥 Applying LED pattern for {status}: {pattern}")
        
        # Apply all LED states - this ensures solid LEDs are set correctly
        # even when transitioning from blinking states
        for color, mode in pattern.items():
            if mode == 'solid':
                self.set_led(color, True)
                logger.debug(f"🚥 Set {color} LED to SOLID ON")
            elif mode == 'off':
                self.set_led(color, False)
                logger.debug(f"🚥 Set {color} LED to OFF")
            # 'blink' mode is handled by the blink control loop

    def _blink_control_loop(self):
        while self.running:
            try:
                self.blink_state = not self.blink_state
                if self.current_status in self.status_patterns:
                    pattern = self.status_patterns[self.current_status]
                    for color, mode in pattern.items():
                        if mode == 'blink':
                            self.set_led(color, self.blink_state)
                time.sleep(0.5) # Consistent blink speed (discovery mode speed)
            except Exception as e:
                logger.error(f"❌ Error in blink control: {e}")
                time.sleep(1)

    def _status_watcher_loop(self):
        logger.info(f"🚥 Watching for status changes in {self.status_file}")
        while self.running:
            try:
                if os.path.exists(self.status_file):
                    with open(self.status_file, 'r') as f:
                        new_status = f.read().strip()
                    if new_status and new_status != self.current_status:
                        logger.info(f"🚥 Status change detected: {self.current_status} -> {new_status}")
                        self.current_status = new_status
                        self._apply_status_pattern(new_status)
                time.sleep(0.05)  # Check 20 times per second for INSTANT response
            except Exception as e:
                logger.error(f"❌ Error in status watcher: {e}")
                time.sleep(1)

    def start(self):
        if not self.setup_gpio():
            logger.error("❌ Cannot start LED controller, GPIO setup failed.")
            return

        # Set initial status
        self._apply_status_pattern(self.current_status)

        self.blink_thread = threading.Thread(target=self._blink_control_loop, daemon=True)
        self.blink_thread.start()
        
        self.status_thread = threading.Thread(target=self._status_watcher_loop, daemon=True)
        self.status_thread.start()
        
        logger.info("✅ LED Controller started.")

    def stop(self):
        self.running = False
        logger.info("🛑 Stopping LED controller...")
        self.cleanup_gpio()

    def cleanup_gpio(self):
        """PRODUCTION FIX: Properly clean up GPIO resources to prevent 'GPIO busy' errors"""
        try:
            logger.info("🚥 Starting GPIO cleanup...")

            # Turn off all LEDs first
            for color in self.led_pins.keys():
                self.set_led(color, False)

            if self.gpio_lib == "lgpio":
                # Properly release lgpio resources
                try:
                    import lgpio
                    for color, gpio_obj in self.gpio_objects.items():
                        try:
                            chip = gpio_obj['chip']
                            pin = gpio_obj['pin']
                            lgpio.gpio_write(chip, pin, 0)  # Turn off
                            lgpio.gpio_free(chip, pin)      # Free the pin
                        except Exception as e:
                            logger.debug(f"lgpio cleanup {color}: {e}")

                    # Close chip handles
                    closed_chips = set()
                    for gpio_obj in self.gpio_objects.values():
                        chip = gpio_obj['chip']
                        if chip not in closed_chips:
                            try:
                                lgpio.gpiochip_close(chip)
                                closed_chips.add(chip)
                            except Exception as e:
                                logger.debug(f"lgpio chip close: {e}")
                except ImportError:
                    logger.debug("lgpio not available for cleanup")

            elif self.gpio_lib == "gpiozero":
                # Properly close gpiozero LEDs
                for color, gpio_obj in self.gpio_objects.items():
                    try:
                        led = gpio_obj['led']
                        led.off()    # Turn off first
                        led.close()  # Then close
                    except Exception as e:
                        logger.debug(f"gpiozero cleanup {color}: {e}")

            # Clear objects
            self.gpio_objects.clear()
            logger.info("🚥 GPIO cleanup complete")

        except Exception as e:
            logger.warning(f"GPIO cleanup warning: {e}")

def set_led_status(status: str):
    """Helper function to be used by other scripts"""
    try:
        with open("/tmp/led_status", 'w') as f:
            f.write(status)
    except Exception as e:
        logger.error(f"Failed to write LED status: {e}")

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    
    # Create status file for testing
    if not os.path.exists("/tmp"):
        os.mkdir("/tmp")

    controller = LEDController()
    controller.start()
    
    # Check if we're running in daemon mode (no arguments) or test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test mode - run test sequence and exit
        set_led_status("booting")
        try:
            test_statuses = ['ble_advertising', 'wifi_connecting', 'wifi_connected', 'factory_reset', 'error', 'shutdown']
            for status in test_statuses:
                print(f"--- Setting status to: {status} ---")
                set_led_status(status)
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        finally:
            controller.stop()
            print("Test complete.")
    else:
        # Daemon mode - run continuously
        logger.info("🚥 LED Controller running in daemon mode")
        set_led_status("booting")
        try:
            # Keep running until interrupted
            while controller.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 LED Controller interrupted")
        finally:
            controller.stop()
            logger.info("🛑 LED Controller stopped")