import json
import os
import yaml
from typing import Dict, Any, Optional
from logger import logger, setup_logger

class ConfigManager:
    """Manages add-on configuration, reading from Supervisor or local fallbacks."""
    
    def __init__(self, options_path: str = "/data/options.json"):
        self.options_path = options_path
        self.config: Dict[str, Any] = {
            "apps_script_url": "",
            "hub_id": "",
            "custom_storage_url": "http://homeassistant:8100",
            "ha_token": "",
            "debug": False
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

    def _apply_dict(self, data: Dict[str, Any]):
        """Helper to safely apply dictionary options to config."""
        for key in self.config.keys():
            if key in data:
                val = data[key]
                if key == "debug":
                    self.config[key] = str(val).lower() == "true" or val is True
                else:
                    self.config[key] = str(val) if val is not None else ""

    def _apply_env(self):
        """Helper to load config fields from environment variables."""
        for key in self.config.keys():
            env_key = f"HA_DATA_COLLECTOR_{key.upper()}"
            # Support standard prefix or just the variable name
            fallback_key = key.upper()
            val = os.getenv(env_key) or os.getenv(fallback_key)
            if val is not None:
                if key == "debug":
                    self.config[key] = str(val).lower() in ("true", "1", "yes")
                else:
                    self.config[key] = str(val)

    @property
    def apps_script_url(self) -> str:
        return self.config["apps_script_url"]

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
