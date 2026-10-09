import json
import os
import yaml
from typing import Dict, Any, Optional
from logger import logger, setup_logger

class ConfigManager:
    """Manages add-on configuration, reading from Supervisor or local fallbacks."""

    # Options that must not be coerced to strings.
    _BOOL_KEYS = ("debug", "enable_dock_telemetry")
    _INT_KEYS = ("dock_cluster_id", "dock_poll_interval", "dock_min_write_interval")

    def __init__(self, options_path: str = "/data/options.json"):
        self.options_path = options_path
        self.config: Dict[str, Any] = {
            "hub_id": "",
            "custom_storage_url": "http://homeassistant:8100",
            "ha_token": "",
            "debug": False,

            # --- Dock telemetry (Matter Server custom cluster counters) ---
            "enable_dock_telemetry": True,
            "matter_server_url": "ws://core-matter-server:5580/ws",
            # ProductName prefixes that identify a dock (Basic Information
            # cluster 40, attribute 3). Prefix match, so Dock_6D and Dock_4D
            # both qualify.
            "dock_product_names": "Dock_",
            # Vendor-specific counter cluster. 0 = auto-detect only. The default
            # is 0xFFF1FC21; a firmware vendor-ID change moves this, which is
            # why auto-detection always runs as a fallback.
            "dock_cluster_id": 4294048801,
            "dock_endpoints": "1-6",
            # Reconciliation live-read interval, seconds.
            "dock_poll_interval": 900,
            # Debounce window, seconds — coalesces the counters a single press
            # bumps into one row.
            "dock_min_write_interval": 2,
        }
        self.load_config()
        
    def load_config(self):
        """Loads configuration from Supervisor options, environment, or config.yaml."""
        # 1. Try Supervisor options.json
        if os.path.exists(self.options_path):
            try:
                with open(self.options_path, "r") as f:
                    opts = json.load(f)
                    logger.info("Loaded configuration from Supervisor options.json")
                    self._apply_dict(opts)
                    # Reconfigure default logger if debug level has changed
                    setup_logger("data_collector", self.config["debug"])
                    return
            except Exception as e:
                logger.warning(f"Failed to read options.json at {self.options_path}: {e}")

        # 2. Try Local config.yaml fallback (for developer machine testing)
        local_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
        if os.path.exists(local_config_path):
            try:
                with open(local_config_path, "r") as f:
                    opts = yaml.safe_load(f)
                    if opts and "options" in opts:
                        logger.info(f"Loaded configuration from local {local_config_path} options key")
                        self._apply_dict(opts["options"])
                    elif opts:
                        logger.info(f"Loaded configuration from local {local_config_path} root keys")
                        self._apply_dict(opts)
                    setup_logger("data_collector", self.config["debug"])
                    return
            except Exception as e:
                logger.warning(f"Failed to read local config.yaml: {e}")

        # 3. Try Environment Variables
        logger.info("Checking environment variables for config fallbacks")
        self._apply_env()
        setup_logger("data_collector", self.config["debug"])

    def _coerce(self, key: str, val: Any) -> Any:
        """Coerces a raw option value to the type its default declares."""
        if key in self._BOOL_KEYS:
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("true", "1", "yes", "on")
        if key in self._INT_KEYS:
            try:
                return int(str(val).strip())
            except (TypeError, ValueError):
                logger.warning(f"Option '{key}' value {val!r} is not an integer — keeping current value")
                return self.config[key]
        return str(val) if val is not None else ""

    def _apply_dict(self, data: Dict[str, Any]):
        """Helper to safely apply dictionary options to config."""
        for key in self.config.keys():
            if key in data:
                self.config[key] = self._coerce(key, data[key])

    def _apply_env(self):
        """Helper to load config fields from environment variables."""
        for key in self.config.keys():
            env_key = f"HA_DATA_COLLECTOR_{key.upper()}"
            # Support standard prefix or just the variable name
            fallback_key = key.upper()
            val = os.getenv(env_key) or os.getenv(fallback_key)
            if val is not None:
                self.config[key] = self._coerce(key, val)

    @property
    def hub_id(self) -> str:
        return self.config["hub_id"]
        
    @hub_id.setter
    def hub_id(self, value: str):
        self.config["hub_id"] = value

    @property
    def custom_storage_url(self) -> str:
        return self.config["custom_storage_url"]

    @property
    def ha_token(self) -> str:
        return self.config["ha_token"]

    @property
    def debug(self) -> bool:
        return self.config["debug"]

    # ------------------------------------------------------------------ #
    # Dock telemetry
    # ------------------------------------------------------------------ #

    @property
    def enable_dock_telemetry(self) -> bool:
        return self.config["enable_dock_telemetry"]

    @property
    def matter_server_url(self) -> str:
        return self.config["matter_server_url"]

    @property
    def dock_product_names(self) -> list:
        raw = self.config["dock_product_names"] or "Dock_"
        names = [part.strip() for part in str(raw).split(",") if part.strip()]
        return names or ["Dock_"]

    @property
    def dock_cluster_id(self) -> int:
        return int(self.config["dock_cluster_id"] or 0)

    @property
    def dock_endpoints(self) -> str:
        return self.config["dock_endpoints"] or "1-6"

    @property
    def dock_poll_interval(self) -> int:
        return int(self.config["dock_poll_interval"] or 900)

    @property
    def dock_min_write_interval(self) -> int:
        return int(self.config["dock_min_write_interval"] or 0)
