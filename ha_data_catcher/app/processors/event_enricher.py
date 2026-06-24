import json
from typing import Dict, Any, Optional
from logger import logger

class EventEnricher:
    """Enriches baseline parsed events with Custom Storage metadata and HA registry mappings."""
    
    def __init__(self):
        # Local cache of HA registries (updated by the websocket collector)
        self.ha_entity_registry: Dict[str, Dict[str, Any]] = {}
        self.ha_device_registry: Dict[str, Dict[str, Any]] = {}
        self.ha_area_registry: Dict[str, Dict[str, Any]] = {}
        self.ha_floor_registry: Dict[str, Dict[str, Any]] = {}

    def update_ha_registries(
        self,
        entities: Dict[str, Dict[str, Any]],
        devices: Dict[str, Dict[str, Any]],
        areas: Dict[str, Dict[str, Any]],
        floors: Dict[str, Dict[str, Any]]
    ):
        """Updates internal caches of HA native registries."""
        self.ha_entity_registry = entities
        self.ha_device_registry = devices
        self.ha_area_registry = areas
        self.ha_floor_registry = floors
        logger.debug(f"HA Registries updated: {len(entities)} entities, {len(devices)} devices")

    def resolve_matter_node_id(self, entity_id: Optional[str] = None, device_id: Optional[str] = None) -> Optional[str]:
        """Resolves an entity ID or Device ID to its Matter Node ID using the device registry."""
        if not device_id and entity_id:
            entity_info = self.ha_entity_registry.get(entity_id)
            if entity_info:
                device_id = entity_info.get("device_id")
                
        if not device_id:
            return None
            
        device_info = self.ha_device_registry.get(device_id)
        if not device_info:
            return None
            
        # HA Matter devices store the node ID in device identifiers
        # Format: [["matter", "1-3"]] or similar, where 1-3 is node_id
        identifiers = device_info.get("identifiers", [])
        for id_type, id_val in identifiers:
            if id_type == "matter":
                logger.debug(f"Resolved Matter Node ID '{id_val}' for device '{device_id}'")
                return str(id_val)
        return None

    def _match_matter_node_id(self, ha_node_id: Optional[str], custom_node_id: Optional[str]) -> bool:
        if not ha_node_id or not custom_node_id:
            return False
        
        ha_node_str = str(ha_node_id).strip().lower()
        custom_node_str = str(custom_node_id).strip().lower()
        
        if ha_node_str == custom_node_str:
            return True
            
        # Extract numeric suffixes (e.g. "3" from "1-3" or "matter_node_3")
        import re
        def get_numeric_suffix(s: str) -> Optional[str]:
            match = re.search(r'(\d+)\s*$', s)
            return match.group(1) if match else None
            
        ha_num = get_numeric_suffix(ha_node_str)
        custom_num = get_numeric_suffix(custom_node_str)
        
        if ha_num and custom_num and ha_num == custom_num:
            return True
            
        return False

    def enrich_event(
        self,
        parsed_event: Dict[str, Any],
        custom_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enriches parsed event fields using custom storage and HA registries.
        """
        enriched = parsed_event.copy()
        entity_id = enriched.get("entity_id")
        
        # 1. Resolve basic HA registry fields
        device_id: Optional[str] = None
        area_id: Optional[str] = None
        manufacturer: Optional[str] = None
        model: Optional[str] = None
        platform: Optional[str] = None
        integration: Optional[str] = None
        
        if entity_id:
            entity_entry = self.ha_entity_registry.get(entity_id)
            if entity_entry:
                device_id = entity_entry.get("device_id")
                area_id = entity_entry.get("area_id")
                platform = entity_entry.get("platform")
                integration = platform # Usually matches platform
                
        if not device_id:
            device_id = enriched.get("device_id")
            
        if device_id:
            device_entry = self.ha_device_registry.get(device_id)
            if device_entry:
                manufacturer = device_entry.get("manufacturer")
                model = device_entry.get("model")
                # If entity didn't define an area_id, check the parent device
                if not area_id:
                    area_id = device_entry.get("area_id")

        enriched.update({
            "device_id": device_id
        })

        # 2. Extract Matter node ID
        matter_node_id = self.resolve_matter_node_id(entity_id=entity_id, device_id=device_id)
        is_matter = bool(matter_node_id) or (platform == "matter")
        
        # 3. Resolve Snap / Dock structures from Custom Storage
        is_snap = False
        is_dock = False
        room_id: Optional[str] = None
        device_type: Optional[str] = None
        friendly_name = enriched.get("friendly_name")
        
        # Fetch maps from Custom Storage metadata
        snaps = custom_metadata.get("snaps", {})
        docks = custom_metadata.get("docks", {})
        room_map = custom_metadata.get("rooms", {})
        
        # Try finding snap match
        snap_match = None
        matched_sub_device = None
        
        if entity_id:
            for s_id, s_data in snaps.items():
                # Check root entity_id
                if s_data.get("entity_id") == entity_id:
                    snap_match = (s_id, s_data)
                    break
                # Check sub_devices list
                sub_devices = s_data.get("sub_devices", [])
                for sub_dev in sub_devices:
                    if sub_dev.get("entity_id") == entity_id:
                        snap_match = (s_id, s_data)
                        matched_sub_device = sub_dev
                        break
                if snap_match:
                    break
                    
        # If no entity_id match, try by matter_node_id
        if not snap_match and matter_node_id:
            for s_id, s_data in snaps.items():
                if self._match_matter_node_id(matter_node_id, s_data.get("matter_node_id")):
                    snap_match = (s_id, s_data)
                    break
                    
        # Strict matching only. No suffix/substring fallbacks.

        if snap_match:
            s_id, s_data = snap_match
            is_snap = True
            room_id = s_data.get("room_id")
            
            # If we matched a specific sub-device, use its load_type and name
            if matched_sub_device:
                device_type = matched_sub_device.get("load_type", s_data.get("type", "dimmer"))
                friendly_name = matched_sub_device.get("name", s_data.get("label"))
            else:
                device_type = s_data.get("type", "dimmer")
                if s_data.get("label"):
                    friendly_name = s_data["label"]
                    
            enriched["log_source"] = f"snap:{s_id}"
            if not matter_node_id:
                matter_node_id = s_data.get("matter_node_id")
        # (Fallback removed: Do not rely on 'snap' in entity_id or friendly_name)
            
        # Try finding dock match
        dock_match = None
        matched_docklet = None
        
        if entity_id:
            for d_id, d_data in docks.items():
                if d_data.get("entity_id") == entity_id:
                    dock_match = (d_id, d_data)
                    break
                # Check docklets
                docklets = d_data.get("docklets", {})
                if isinstance(docklets, dict):
                    for docklet_id, docklet_data in docklets.items():
                        if docklet_data.get("entity_id") == entity_id:
                            dock_match = (d_id, d_data)
                            matched_docklet = docklet_data
                            break
                        if docklet_data.get("bound_device_entity_id") == entity_id:
                            dock_match = (d_id, d_data)
                            matched_docklet = docklet_data
                            break
                if dock_match:
                    break
                    
        if not dock_match and matter_node_id:
            for d_id, d_data in docks.items():
                if self._match_matter_node_id(matter_node_id, d_data.get("matter_node_id")):
                    dock_match = (d_id, d_data)
                    break
                    
        # Strict matching only. No suffix/substring fallbacks.
                    
        if dock_match:
            d_id, d_data = dock_match
            is_dock = True
            
            # Prefer room_id from dock metadata if not already resolved by snap_match
            if not room_id:
                room_id = d_data.get("room_id")
                
            # If we matched a specific docklet slot, set appropriate device_type and friendly_name
            if matched_docklet:
                # If event is on the slot itself
                if matched_docklet.get("entity_id") == entity_id:
                    device_type = "docklet"
                    docklet_name = matched_docklet.get("bound_device_label") or matched_docklet.get("name")
                    if docklet_name and docklet_name != "not_mapped":
                        friendly_name = docklet_name
                    # Set a flag in enriched so metrics/parsers know this is a docklet slot event
                    enriched["is_docklet_slot_event"] = True
                # If event is on the bound device
                elif matched_docklet.get("bound_device_entity_id") == entity_id:
                    bound_label = matched_docklet.get("bound_device_label")
                    if bound_label and bound_label != "not_mapped":
                        friendly_name = bound_label
            
            if not device_type or device_type == "not_mapped":
                device_type = "dock"
                dock_label = d_data.get("label")
                if dock_label and dock_label != "not_mapped":
                    friendly_name = dock_label
                    
            enriched["log_source"] = f"dock:{d_id}"
            if not matter_node_id:
                matter_node_id = d_data.get("matter_node_id")
        # (Fallback removed: Do not rely on 'dock' or 'docklet' in entity_id or friendly_name)

        # Re-evaluate is_matter in case matter_node_id was updated from Custom Storage
        if matter_node_id:
            is_matter = True

        # If log source was not set by snap or dock, use HA entity domain
        if "log_source" not in enriched or enriched["log_source"] == "websocket":
            domain = enriched.get("domain") or "system"
            enriched["log_source"] = f"ha:{domain}"

        # 4. Resolve Room and Floor Mappings
        room_name: Optional[str] = None
        floor_name: Optional[str] = None
        
        if room_id and room_map:
            room_info = room_map.get(room_id, {})
            room_name = room_info.get("name")
            floor_name = room_info.get("floor_name")

        # Fallback to domain classification for Device Type
        if (not device_type or device_type == "not_mapped") and entity_id:
            domain = enriched.get("domain")
            if domain == "light":
                device_type = "Light"
            elif domain == "fan":
                device_type = "Fan"
            elif domain == "switch":
                device_type = "Switch"
            elif domain == "cover":
                device_type = "Cover"
            elif domain == "lock":
                device_type = "Lock"
            elif domain == "climate":
                device_type = "Climate"
            elif domain == "media_player":
                device_type = "Media Player"
            elif domain == "automation":
                device_type = "Automation"
            elif domain == "scene":
                device_type = "Scene"
            else:
                device_type = domain.capitalize() if domain else "Unknown"

        # Apply fallback overrides
        enriched.update({
            "friendly_name": friendly_name,
            "room": room_name,
            "floor": floor_name,
            "device_type": device_type or "Unknown"
        })

        # 5. Extract Timing Metric Indicators (from metrics_fields)
        # Import dynamically to avoid circular dependencies
        from processors.metrics_fields import MetricsFieldsExtractor
        metrics_extractor = MetricsFieldsExtractor()
        metrics = metrics_extractor.extract_metrics(
            event_type=enriched["ha_event_type"],
            parsed_event=enriched,
            is_snap=is_snap,
            is_dock=is_dock,
            is_matter=is_matter,
            thread_node_id=matter_node_id # node ID is used as thread_node_id reference
        )
        enriched.update(metrics)

        # 6. Apply Use Case Detection
        raw_event = json.loads(enriched["raw_event_json"])
        raw_context = raw_event.get("context", {})
        
        from processors.use_case_detector import UseCaseDetector
        detector = UseCaseDetector()
        use_case = detector.detect_use_case(
            event_type=enriched["ha_event_type"],
            event_data=raw_event.get("data", {}),
            context={
                "user_id": raw_context.get("user_id"),
                "parent_id": raw_context.get("parent_id")
            },
            is_snap=is_snap,
            is_dock=is_dock,
            is_matter=is_matter
        )
        enriched["use_case"] = use_case

        return enriched
