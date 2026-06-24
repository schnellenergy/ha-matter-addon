from typing import Dict, Any, Optional
from logger import logger

class MetricsFieldsExtractor:
    """Extracts telemetry metric fields needed for downstream latency and reliability analytics."""
    
    def __init__(self):
        pass

    def extract_metrics(
        self,
        event_type: str,
        parsed_event: Dict[str, Any],
        is_snap: bool,
        is_dock: bool,
        is_matter: bool,
        thread_node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Populates metric fields:
            docklet_state_change_ts
            matter_command_ts
            snap_state_change_ts
            thread_node_id
        """
        timestamp = parsed_event.get("timestamp")
        entity_id = parsed_event.get("entity_id") or ""
        friendly_name = parsed_event.get("friendly_name") or ""
        log_source = parsed_event.get("log_source") or ""
        
        is_snap_check = is_snap
        is_dock_check = is_dock
        
        docklet_state_change_ts: Optional[str] = None
        matter_command_ts: Optional[str] = None
        snap_state_change_ts: Optional[str] = None
        
        # 1. State changes at Dock level (buttons, sensors on dock)
        if (is_dock_check or parsed_event.get("is_docklet_slot_event")) and event_type == "state_changed":
            docklet_state_change_ts = timestamp
            
        # 2. Command triggers (Matter level)
        if is_matter:
            if event_type in ("call_service", "state_changed"):
                matter_command_ts = timestamp
                
        # 3. Snap switch state changes
        if is_snap_check and event_type == "state_changed" and not parsed_event.get("is_docklet_slot_event"):
            snap_state_change_ts = timestamp

        # If it's a matter event or zha_event, set command timestamp
        if event_type in ("matter_event", "zha_event", "deconz_event"):
            matter_command_ts = timestamp
            
        return {
            "docklet_state_change_ts": docklet_state_change_ts,
            "matter_command_ts": matter_command_ts,
            "snap_state_change_ts": snap_state_change_ts,
            "thread_node_id": thread_node_id
        }
