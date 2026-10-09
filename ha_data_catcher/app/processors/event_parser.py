import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo
from logger import logger

def extract_color(data_dict: Dict[str, Any]) -> Optional[str]:
    if "color_name" in data_dict:
        return str(data_dict["color_name"])
    if "color_temp_kelvin" in data_dict:
        try:
            return f"{int(data_dict['color_temp_kelvin'])}K"
        except Exception:
            pass
    if "color_temp" in data_dict:
        try:
            mireds = float(data_dict['color_temp'])
            if mireds > 0:
                return f"{int(round(1000000.0 / mireds))}K"
        except Exception:
            pass
    if "rgb_color" in data_dict:
        try:
            return f"RGB{tuple(int(c) for c in data_dict['rgb_color'])}"
        except Exception:
            pass
    if "hs_color" in data_dict:
        try:
            return f"HS{tuple(round(float(c), 1) for c in data_dict['hs_color'])}"
        except Exception:
            pass
    if "xy_color" in data_dict:
        try:
            return f"XY{tuple(round(float(c), 3) for c in data_dict['xy_color'])}"
        except Exception:
            pass
    return None

def extract_fan_speed(data_dict: Dict[str, Any]) -> Optional[str]:
    if "percentage" in data_dict:
        try:
            return f"{int(round(float(data_dict['percentage'])))}%"
        except (ValueError, TypeError):
            pass
    if "preset_mode" in data_dict:
        return str(data_dict["preset_mode"])
    if "speed" in data_dict:
        return str(data_dict["speed"])
    return None

class EventParser:
    """Parses raw Home Assistant events to extract baseline telemetry fields."""
    
    def __init__(self, timezone_name: str = "Asia/Kolkata"):
        self.tz = ZoneInfo(timezone_name)
        logger.info(f"EventParser configured with timezone: {timezone_name}")

    def parse_iso_timestamp(self, ts_str: Optional[str]) -> datetime:
        """Parses an ISO 8601 timestamp string from Home Assistant, returning a local datetime."""
        if not ts_str:
            return datetime.now(self.tz)
            
        try:
            # Home Assistant timestamps are UTC and end with Z or +00:00
            # Replace Z with +00:00 for older Python compatibility if needed
            clean_ts = ts_str.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(clean_ts)
            # Convert to local timezone
            return dt_utc.astimezone(self.tz)
        except Exception as e:
            logger.warning(f"Error parsing timestamp '{ts_str}': {e}. Using current time.")
            return datetime.now(self.tz)

    def parse_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses raw event data into normalized baseline fields.
        Does not enrich using external registries (that is done by EventEnricher).
        """
        event_type = raw_event.get("event_type", "unknown")
        event_data = raw_event.get("data", {})
        context = raw_event.get("context", {})
        time_fired = raw_event.get("time_fired")

        # Parse timestamp
        dt_local = self.parse_iso_timestamp(time_fired)

        # Unique id for this event record — used as Firestore doc id and join key
        event_id = str(uuid.uuid4())

        # Extract context
        context_id = context.get("id") or None
        context_user_id = context.get("user_id") or None
        
        # Initialize default fields
        entity_id: Optional[str] = None
        friendly_name: Optional[str] = None
        old_state: Optional[str] = None
        new_state: Optional[str] = None
        brightness: Optional[int] = None
        fan_speed: Optional[str] = None
        color_name: Optional[str] = None
        action: Optional[str] = None
        origin = raw_event.get("origin", "LOCAL")
        attributes: Dict[str, Any] = {}
        device_id: Optional[str] = event_data.get("device_id")
        
        # Handle state_changed event
        if event_type == "state_changed":
            entity_id = event_data.get("entity_id")
            old_state_obj = event_data.get("old_state") or {}
            new_state_obj = event_data.get("new_state") or {}
            
            old_state = old_state_obj.get("state") if old_state_obj else None
            new_state = new_state_obj.get("state") if new_state_obj else None
            
            # Attributes are preferred from new state, fallback to old
            attributes = new_state_obj.get("attributes", {}) if new_state_obj else old_state_obj.get("attributes", {})
            friendly_name = attributes.get("friendly_name")
            
            # Extract brightness (percentage 0-100)
            if "brightness" in attributes:
                try:
                    raw_brightness = float(attributes["brightness"])
                    brightness = int(round((raw_brightness / 255.0) * 100.0))
                except (ValueError, TypeError):
                    pass
            elif "brightness_pct" in attributes:
                try:
                    brightness = int(round(float(attributes["brightness_pct"])))
                except (ValueError, TypeError):
                    pass
            elif entity_id and entity_id.startswith("number.") and ("level" in entity_id or "brightness" in entity_id) and new_state:
                try:
                    max_val = float(attributes.get("max", 100.0))
                    val = float(new_state)
                    if max_val > 0:
                        brightness = int(round((val / max_val) * 100.0))
                except (ValueError, TypeError):
                    pass
                    
            # Extract fan speed percentage or preset mode
            fan_speed = extract_fan_speed(attributes)
                
            # Extract color information
            color_name = extract_color(attributes)
                
            # Determine Action, checking for custom/binding actions in attributes
            attr_action = None
            for act_key in ("binding_action", "action", "click", "command", "event"):
                if act_key in attributes and attributes[act_key]:
                    attr_action = str(attributes[act_key])
                    break
                    
            if attr_action:
                action = attr_action
            elif old_state != new_state:
                if old_state in ("off", "unavailable", "unknown") and new_state not in ("off", "unavailable", "unknown"):
                    action = "turn_on"
                elif old_state not in ("off", "unavailable", "unknown") and new_state in ("off", "unavailable", "unknown"):
                    action = "turn_off"
                else:
                    action = "state_transition"
            else:
                action = "attribute_update"

        # Handle call_service event
        elif event_type == "call_service":
            domain = event_data.get("domain")
            service = event_data.get("service")
            service_data = event_data.get("service_data", {})
            
            action = f"{domain}.{service}"
            
            # Resolve entity_id from service data (could be string or list)
            srv_entity_id = service_data.get("entity_id")
            if isinstance(srv_entity_id, list) and srv_entity_id:
                entity_id = srv_entity_id[0]
            elif isinstance(srv_entity_id, str):
                entity_id = srv_entity_id
                
            # Extract custom/binding actions in service_data
            for act_key in ("binding_action", "action", "click", "command"):
                if act_key in service_data and service_data[act_key]:
                    action = str(service_data[act_key])
                    break
                    
            # Extract brightness from service call
            if "brightness" in service_data:
                try:
                    raw_brightness = float(service_data["brightness"])
                    brightness = int(round((raw_brightness / 255.0) * 100.0))
                except (ValueError, TypeError):
                    pass
            elif "brightness_pct" in service_data:
                try:
                    brightness = int(round(float(service_data["brightness_pct"])))
                except (ValueError, TypeError):
                    pass
            
            # Extract fan speed from service call
            fan_speed = extract_fan_speed(service_data)
            
            # Extract color name from service call
            color_name = extract_color(service_data)

        # Handle automation_triggered or script_started
        elif event_type in ("automation_triggered", "script_started"):
            entity_id = event_data.get("entity_id") or event_data.get("name")
            friendly_name = event_data.get("name")
            action = "trigger"
            new_state = "triggered"

        # General Event Fallback
        else:
            entity_id = event_data.get("entity_id")
            # Try to extract action from event_data
            for act_key in ("binding_action", "action", "click", "command", "event", "click_type"):
                if act_key in event_data and event_data[act_key]:
                    action = str(event_data[act_key])
                    break
            if not new_state and action:
                new_state = action

        # Fallback domain derivation if entity_id exists
        domain = entity_id.split(".")[0] if entity_id and "." in entity_id else None

        # Build baseline parsed dictionary
        return {
            "event_id": event_id,
            "timestamp": dt_local.isoformat(),
            "date": dt_local.strftime("%Y-%m-%d"),
            "time": dt_local.strftime("%H:%M:%S"),
            "hour": dt_local.hour,
            "day_of_week": dt_local.strftime("%A"),
            "ha_event_type": event_type,
            "entity_id": entity_id,
            "domain": domain,
            "friendly_name": friendly_name,
            "old_state": old_state,
            "new_state": new_state,
            "brightness": brightness,
            "fan_speed": fan_speed,
            "color_name": color_name,
            "action": action,
            "origin": origin,
            "context_id": context_id,
            "context_user_id": context_user_id,
            "attributes": json.dumps(attributes) if attributes else None,
            "raw_event_json": json.dumps(raw_event),
            "device_id": device_id
        }
