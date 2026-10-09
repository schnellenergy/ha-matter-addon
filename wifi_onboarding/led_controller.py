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

import led_states

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
        
        # What the hub IS, after rank arbitration. Ethernet does not affect it.
        self.base_status = "booting"
        # What the LED is actually SHOWING (base, or green while Ethernet is in).
        self.current_status = "booting"
        self.overlay_active = False
        self._event_offset = 0
        # The steady-state value a release left behind, to be ignored once.
        self._stale_steady = None
        self.running = True
        self.blink_thread = None
        self.blink_state = False
        self.status_file = led_states.STATUS_FILE

        # Serialises every GPIO write. The blink loop and the status watcher are
        # separate threads; without this a blink tick could land *after* a state
        # change and paint one frame of the old pattern (a visible wrong colour
        # on every transition).
        self._io_lock = threading.RLock()

        # LED status patterns based on exact project requirements.
        # Modes: 'solid' | 'off' | 'blink' | 'blink_inv'.
        # 'blink_inv' is the inverse phase of 'blink', so pairing the two gives
        # true alternation between two colours rather than both flashing
        # together (which reads as a single magenta flash).
        self.status_patterns = {
            'booting': {'red': 'blink', 'green': 'off', 'blue': 'off'},          # Boot: Blinking red until connection
            'error': {'red': 'blink', 'green': 'off', 'blue': 'off'},           # Error: Blinking red
            'factory_reset': {'red': 'blink', 'green': 'off', 'blue': 'off'},   # Reset in progress: Blinking red
            # Reset refused (hub has no internet, so the cloud IP record cannot
            # be cleared): alternating red/blue so a refused reset is never
            # silently mistaken for a completed one.
            'reset_refused': {'red': 'blink', 'green': 'off', 'blue': 'blink_inv'},

            # Network connected states (highest priority to lowest)
            'ethernet_connected': {'red': 'off', 'green': 'solid', 'blue': 'off'},  # Ethernet: Solid green (highest priority)
            'wifi_connected': {'red': 'off', 'green': 'off', 'blue': 'solid'},      # WiFi only: Solid blue

            # Transitional/connecting states
            'wifi_connecting': {'red': 'solid', 'green': 'off', 'blue': 'off'},    # Boot reconnect: Solid red
            # App-driven provisioning in flight: fast blinking red until the hub
            # knows the real outcome. Never blue before then.
            'wifi_provisioning': {'red': 'blink', 'green': 'off', 'blue': 'off'},
            'ble_advertising': {'red': 'blink', 'green': 'off', 'blue': 'off'},     # BLE ready: Blinking red (fresh setup)

            # Special states
            'setup_in_progress': {'red': 'blink', 'green': 'off', 'blue': 'blink'}, # Setup: Red+Blue blink
            # Defined so the contract matches the README, but nothing sets these
            # today — the network monitor only reports ethernet / wifi / idle.
            'wifi_no_internet': {'red': 'off', 'green': 'off', 'blue': 'blink'},    # WiFi but no internet: Blinking blue
            'ethernet_no_internet': {'red': 'off', 'green': 'blink', 'blue': 'off'}, # Ethernet but no internet: Blinking green
            'internet_connected': {'red': 'off', 'green': 'off', 'blue': 'solid'},  # WiFi with internet: Solid blue
            'dual_network': {'red': 'off', 'green': 'solid', 'blue': 'off'},       # Both networks: Ethernet priority (solid green)
            'shutdown': {'red': 'off', 'green': 'off', 'blue': 'off'},             # Shutdown: All off
        }

        # Per-state blink half-period in seconds.
        #
        # Fast blink is reserved for ONE meaning: an in-flight Wi-Fi
        # provisioning attempt. Factory reset uses the normal blink, matching
        # the documented behaviour — the reset already has unambiguous context
        # (the user is holding the button), so a second fast-blink state only
        # diluted what "fast" tells you.
        self._default_blink_interval = 0.5
        self.blink_intervals = {
            'wifi_provisioning': 0.15,
            'reset_refused': 0.25,
        }

    def _blink_interval(self, status: str) -> float:
        return self.blink_intervals.get(status, self._default_blink_interval)

    def _displayed(self) -> str:
        """What the LED should show: green whenever Ethernet is connected,
        otherwise whatever the hub actually is."""
        return 'ethernet_connected' if self.overlay_active else self.base_status

    def _refresh_display(self, reason: str = ''):
        """Repaint if the displayed state has changed."""
        want = self._displayed()
        if want == self.current_status:
            return
        logger.info(
            f"🚥 LED: {self.current_status} -> {want}"
            f"{' (' + reason + ')' if reason else ''}")
        self.current_status = want
        self._apply_status_pattern(want)

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
            with self._io_lock:
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

    def _apply_status_pattern(self, status: str):
        if status not in self.status_patterns:
            logger.warning(f"⚠️ Unknown status pattern: {status}")
            return

        pattern = self.status_patterns[status]
        logger.info(f"🚥 Applying LED pattern for {status}: {pattern}")

        # Hold the IO lock across the whole transition so a concurrent blink
        # tick cannot interleave and leave a colour from the previous pattern
        # lit. Also restart the blink phase from a known point, so every state
        # begins its blink at the same place instead of inheriting the old
        # phase mid-cycle.
        with self._io_lock:
            self.blink_state = False
            # Apply all LED states - this ensures solid LEDs are set correctly
            # even when transitioning from blinking states
            for color, mode in pattern.items():
                if mode == 'solid':
                    self.set_led(color, True)
                elif mode == 'off':
                    self.set_led(color, False)
                elif mode == 'blink':
                    self.set_led(color, False)
                elif mode == 'blink_inv':
                    self.set_led(color, True)
            # 'blink'/'blink_inv' phases are advanced by the blink control loop

    def _blink_control_loop(self):
        while self.running:
            try:
                status = self.current_status
                with self._io_lock:
                    self.blink_state = not self.blink_state
                    pattern = self.status_patterns.get(status)
                    if pattern:
                        for color, mode in pattern.items():
                            if mode == 'blink':
                                self.set_led(color, self.blink_state)
                            elif mode == 'blink_inv':
                                self.set_led(color, not self.blink_state)
                # Interval is per-state: "busy" states blink fast, idle blinks slow.
                time.sleep(self._blink_interval(status))
            except Exception as e:
                logger.error(f"❌ Error in blink control: {e}")
                time.sleep(1)

    def _status_watcher_loop(self):
        """Sole reader of the status file, and therefore the arbiter.

        A write is accepted only if it ranks at least as high as the state
        currently displayed, or if it is explicitly forced (the owner of a
        transient state releasing it). This is what stops the 0.5 s network
        monitor from erasing 'factory_reset' or 'wifi_provisioning'.
        """
        logger.info(f"🚥 Watching for status changes in {self.status_file}")
        last_rejected = None
        while self.running:
            try:
                # Forced releases first, and they are CONSUMED. A release hands
                # the LED back from a transient state, so it must never be lost —
                # if it were, the state being released outranks everything the
                # network monitor can request and the LED would stay stuck on it
                # forever. Its own file means no other writer can clobber it.
                # Ethernet overlay. Purely a display decision — it never
                # touches base_status, so pulling the cable reveals exactly the
                # state the hub was in all along.
                overlay = led_states.read_overlay()
                if overlay != self.overlay_active:
                    self.overlay_active = overlay
                    self._refresh_display('ethernet in' if overlay else 'ethernet out')

                # Events next, in order. These are never dropped, so a factory
                # reset always shows and a release always lands.
                events, self._event_offset = led_states.read_events(self._event_offset)
                for status, forced in events:
                    if status == self.base_status:
                        continue
                    if forced or led_states.rank(status) >= led_states.rank(self.base_status):
                        previous = self.base_status
                        self.base_status = status
                        self._refresh_display('forced' if forced else 'event')
                        last_rejected = None
                        # The steady-state slot may still hold the state we just
                        # left — often a higher-ranked one — which would undo this
                        # on the very next read. Remember it and ignore exactly
                        # that value until the monitor reports something newer.
                        # (Rewriting the slot instead would discard a fresher
                        # report that had already landed.)
                        self._stale_steady = previous
                    else:
                        logger.debug(
                            f"🚥 Held '{self.base_status}'; ignored lower-ranked event '{status}'")

                if os.path.exists(self.status_file):
                    with open(self.status_file, 'r') as f:
                        raw = f.read()

                    new_status, forced = led_states.parse(raw)

                    if new_status is None:
                        if raw.strip() and raw.strip() != last_rejected:
                            last_rejected = raw.strip()
                            logger.error(
                                f"🚥 Ignoring unknown LED state: '{last_rejected}' "
                                f"(LED left on '{self.current_status}')"
                            )
                    elif new_status == self._stale_steady:
                        # The value we were released from, not yet refreshed.
                        pass
                    elif new_status != self.base_status:
                        self._stale_steady = None
                        current_rank = led_states.rank(self.base_status)
                        new_rank = led_states.rank(new_status)
                        if forced or new_rank >= current_rank:
                            self.base_status = new_status
                            self._refresh_display('forced' if forced else '')
                            last_rejected = None
                        elif new_status != last_rejected:
                            # Log once per distinct rejection so a repeating
                            # low-priority writer can't flood the log.
                            last_rejected = new_status
                            logger.debug(
                                f"🚥 Held '{self.base_status}' (rank {current_rank}); "
                                f"rejected lower-ranked '{new_status}' (rank {new_rank})"
                            )
                time.sleep(0.05)  # Check 20 times per second for INSTANT response
            except Exception as e:
                logger.error(f"❌ Error in status watcher: {e}")
                time.sleep(1)

    def start(self):
        # Events or an overlay left by a previous run must not be replayed.
        self._event_offset = led_states.clear_events()
        led_states.set_overlay(False)

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

def set_led_status(status: str, force: bool = False):
    """Helper function to be used by other scripts.

    `force` releases a transient state (see led_states) and should only be used
    by whoever entered it.
    """
    try:
        if not led_states.write_request(status, force):
            logger.error(f"🚥 Refusing to write unknown LED state: '{status}'")
            return
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