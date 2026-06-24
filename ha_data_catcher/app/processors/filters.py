from typing import Dict, Any, Optional

# Configurable lists for filtering noisy telemetry
IGNORED_ENTITY_PREFIXES = [
    "sensor.router_",
    "sensor.network_",
    "sensor.wifi_",
    "sensor.bandwidth_",
    "sensor.ping_",
    "sensor.uptime",
    "sensor.heartbeat",
    "button.ping",
    "update.",
    "binary_sensor.network_",
    "binary_sensor.wifi_",
    "sensor.archer_"
]

IGNORED_DOMAINS = [
    "device_tracker",
    "upnp",
    "sun",
    "zone",
    "weather"
]

IGNORED_EVENT_TYPES = [
    "time_changed",
    "themes_updated",
    "component_loaded",
    "core_config_updated",
    "recorder_5min_statistics_generated",
    "recorder_hourly_statistics_generated"
]

KEEP_DOMAINS = [
    "light",
    "fan",
    "switch",
    "cover",
    "lock",
    "climate",
    "media_player",
    "automation",
    "scene"
]

def should_filter_event(event_type: str, entity_id: Optional[str] = None) -> bool:
    """
    Evaluates whether an event should be filtered out to avoid noise.
    
    Returns:
        True if the event SHOULD be ignored (filtered).
        False if the event SHOULD be kept.
    """
    # 1. Filter by event type
    if event_type in IGNORED_EVENT_TYPES:
        return True
        
    if not entity_id:
        return False
        
    entity_id_lower = entity_id.lower()
    
    # Keep ALL dock binding actions, snap switches, and associated remote logs
    if "dock" in entity_id_lower or "snap" in entity_id_lower:
        return False

    # 2. Extract domain
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    
    # 3. Always keep check (takes precedence over ignored domains)
    if domain in KEEP_DOMAINS:
        # Still check if it starts with ignored prefixes (e.g. sensor.router_light)
        for prefix in IGNORED_ENTITY_PREFIXES:
            if entity_id.startswith(prefix):
                return True
        return False
        
    # 4. Filter by ignored domains
    if domain in IGNORED_DOMAINS:
        return True
        
    # 5. Filter by entity prefixes
    for prefix in IGNORED_ENTITY_PREFIXES:
        if entity_id.startswith(prefix):
            return True
            
    # Check for general diagnostics, wifi, or router entities
    if any(keyword in entity_id_lower for keyword in ["wifi", "ping", "bandwidth", "uptime", "archer", "battery", "charger", "sun"]):
        return True
        
    return False
