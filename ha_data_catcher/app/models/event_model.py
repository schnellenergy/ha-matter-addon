from pydantic import BaseModel
from typing import Optional

class NormalizedEvent(BaseModel):
    """Pydantic model representing a normalized Home Assistant event record."""
    timestamp: str
    date: str
    time: str
    hour: int
    day_of_week: str
    ha_event_type: str
    entity_id: Optional[str] = None
    domain: Optional[str] = None
    friendly_name: Optional[str] = None
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    brightness: Optional[int] = None
    fan_speed: Optional[str] = None
    color_name: Optional[str] = None
    action: Optional[str] = None
    origin: Optional[str] = None
    attributes: Optional[str] = None
    raw_event_json: str
    device_id: Optional[str] = None
    log_source: str
    room: Optional[str] = None
    floor: Optional[str] = None
    device_type: Optional[str] = None
    docklet_state_change_ts: Optional[str] = None
    matter_command_ts: Optional[str] = None
    snap_state_change_ts: Optional[str] = None
    thread_node_id: Optional[str] = None
    use_case: str
    hub_id: str
