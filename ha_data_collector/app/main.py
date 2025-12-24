#!/usr/bin/env python3
"""
Home Assistant Data Collector Add-on
Collects HA events and sends them to Google Sheets
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import threading

import requests
from flask import Flask, render_template, jsonify

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HomeAssistantDataCollector:
    def __init__(self):
        # Required configuration (user must provide)
        self.ha_token = os.getenv('HA_TOKEN')
        self.google_sheets_url = os.getenv('GOOGLE_SHEETS_URL')

        # Optional configuration with smart defaults
        self.collect_historical = os.getenv(
            'COLLECT_HISTORICAL', 'true').lower() == 'true'
        self.batch_size = int(os.getenv('BATCH_SIZE', '100'))
        self.retry_attempts = int(os.getenv('RETRY_ATTEMPTS', '3'))
        self.excluded_domains = os.getenv('EXCLUDED_DOMAINS', '').split(
            ',') if os.getenv('EXCLUDED_DOMAINS') else []
        self.excluded_entities = os.getenv('EXCLUDED_ENTITIES', '').split(
            ',') if os.getenv('EXCLUDED_ENTITIES') else []
        self.include_attributes = os.getenv(
            'INCLUDE_ATTRIBUTES', 'true').lower() == 'true'

        # Auto-configuration for enhanced analytics
        self.timezone_offset = float(
            os.getenv('TIMEZONE_OFFSET', '5.5'))  # IST default
        self.auto_create_headers = os.getenv(
            'AUTO_CREATE_HEADERS', 'true').lower() == 'true'

        # Event deduplication to prevent duplicate button presses
        self.recent_events = {}  # Store recent events to prevent duplicates
        self.processed_events = set()  # Store processed event IDs
        self.dedup_window = 2  # seconds to consider events as duplicates

        # Get Home Assistant URL from environment (set by run.sh)
        # This allows the addon to work with any HA instance
        self.ha_url = os.getenv('HA_URL', 'http://supervisor/core')
        self.websocket_url = os.getenv('HA_WEBSOCKET_URL', 'ws://supervisor/core/websocket')

        # Get supervisor token for add-on authentication
        self.supervisor_token = os.getenv('SUPERVISOR_TOKEN', '')

        logger.info(f"🔑 HA Token: {'✅ Set' if self.ha_token else '❌ Missing'}")
        logger.info(
            f"🔑 Supervisor Token: {'✅ Set' if self.supervisor_token else '❌ Missing'}")
        logger.info(f"🌐 HA URL: {self.ha_url}")
        logger.info(f"🔌 WebSocket URL: {self.websocket_url}")

        self.stats = {
            'events_processed': 0,
            'events_sent': 0,
            'events_received': 0,
            'events_filtered': 0,
            'errors': 0,
            'last_event_time': None,
            'start_time': datetime.now(timezone.utc).isoformat()
        }

        logger.info("Data Collector initialized")
        logger.info(f"Google Sheets URL: {self.google_sheets_url}")
        logger.info(f"Excluded domains: {self.excluded_domains}")
        logger.info(f"Excluded entities: {self.excluded_entities}")
        logger.info(
            f"Event deduplication enabled: {self.dedup_window}s window")

    def get_auth_headers(self):
        """Get authentication headers for Home Assistant API calls"""
        # Always use HA token for direct connection authentication
        if self.ha_token:
            logger.debug(f"🔐 Using HA token for API auth")
            return {
                'Authorization': f'Bearer {self.ha_token}',
                'Content-Type': 'application/json'
            }
        else:
            logger.error("❌ No HA token available for authentication")
            return {
                'Content-Type': 'application/json'
            }

    async def send_to_google_sheets(self, event_data: Dict[str, Any]) -> bool:
        """Send event data to Google Sheets"""
        try:
            headers = {'Content-Type': 'application/json'}

            for attempt in range(self.retry_attempts):
                try:
                    response = requests.post(
                        self.google_sheets_url,
                        json=event_data,
                        headers=headers,
                        timeout=30
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get('status') == 'success':
                            self.stats['events_sent'] += 1
                            logger.debug(
                                f"Successfully sent event: {event_data.get('event_id', 'unknown')}")
                            return True
                        else:
                            logger.error(f"Google Sheets API error: {result}")

                    else:
                        logger.error(
                            f"HTTP error {response.status_code}: {response.text}")

                except requests.exceptions.RequestException as e:
                    logger.error(
                        f"Request failed (attempt {attempt + 1}): {e}")
                    if attempt < self.retry_attempts - 1:
                        # Exponential backoff
                        await asyncio.sleep(2 ** attempt)

            self.stats['errors'] += 1
            return False

        except Exception as e:
            logger.error(f"Error sending to Google Sheets: {e}")
            self.stats['errors'] += 1
            return False

    def is_duplicate_event(self, event: Dict[str, Any]) -> bool:
        """Check if this event is a duplicate of a recent event"""
        try:
            event_type = event.get('event_type', '')
            event_data = event.get('data', {})
            entity_id = event_data.get('entity_id', '')

            # Create a unique key for this event
            if event_type == 'state_changed':
                new_state = event_data.get('new_state', {})
                old_state = event_data.get('old_state', {})

                # For button events, use entity_id + new_state timestamp as key
                if 'button' in entity_id.lower() or 'arre' in entity_id.lower():
                    # Use timestamp for button events to detect exact same press
                    event_key = f"button:{entity_id}:{new_state.get('state', '')}"
                else:
                    # For other events, use entity_id + state change + timestamp
                    timestamp = event.get('time_fired', '')
                    event_key = f"state:{entity_id}:{old_state.get('state', '')}→{new_state.get('state', '')}:{timestamp}"
            else:
                # For non-state events, use event_type + entity_id
                event_key = f"{event_type}:{entity_id}"

            current_time = time.time()

            # Check if we've seen this event recently
            if event_key in self.recent_events:
                last_time = self.recent_events[event_key]
                if current_time - last_time < self.dedup_window:
                    logger.debug(
                        f"🔄 Duplicate event detected: {event_key} (within {self.dedup_window}s)")
                    return True

            # Store this event
            self.recent_events[event_key] = current_time

            # Clean up old events (older than 10 seconds)
            cleanup_time = current_time - 10
            self.recent_events = {
                k: v for k, v in self.recent_events.items() if v > cleanup_time}

            return False

        except Exception as e:
            logger.debug(f"Error in duplicate detection: {e}")
            return False

    def should_process_event(self, event: Dict[str, Any]) -> bool:
        """Check if event should be processed - ONLY DEVICE LOGBOOK EVENTS"""
        event_type = event.get('event_type', '')

        # TEMPORARY: Log all non-state events to debug what we're receiving
        if event_type not in ['state_changed']:
            logger.info(f"🔍 Non-state event received: {event_type}")
            if 'button' in str(event).lower() or 'arre' in str(event).lower():
                logger.info(f"🔘 BUTTON-RELATED EVENT: {event}")

        # ONLY process events that appear in Home Assistant logbook
        logbook_worthy_events = [
            'device_automation',     # Button presses, device triggers
            'zha_event',            # Zigbee device events
            'deconz_event',         # deCONZ device events
            'matter_event',         # Matter device events
            'call_service',         # Service calls (user actions)
            'automation_triggered',  # Automation executions
            'script_started',       # Script executions
            'logbook_entry'         # Direct logbook entries
        ]

        # Process logbook-worthy events
        if event_type in logbook_worthy_events:
            logger.info(f"🔘 LOGBOOK EVENT: {event_type}")
            return True

        # Special handling for state_changed events - only user-controlled devices
        if event_type == 'state_changed':
            data = event.get('data', {})
            entity_id = data.get('entity_id', '')
            new_state = data.get('new_state', {})
            old_state = data.get('old_state', {})

            if not entity_id or not new_state or not old_state:
                return False

            domain = entity_id.split('.')[0] if '.' in entity_id else ''

            # Check for button and arre events specifically
            if 'button' in entity_id.lower() or 'arre' in entity_id.lower():
                # For button events, we want to capture timestamp changes (button presses)
                new_state_value = new_state.get('state')
                old_state_value = old_state.get('state')

                # Button presses usually change the timestamp, not the state value
                # So we check if the timestamp actually changed
                if new_state_value != old_state_value:
                    logger.info(f"🔘 BUTTON PRESS DETECTED: {entity_id}")
                    logger.info(
                        f"   Timestamp: {old_state_value} → {new_state_value}")
                    logger.info(f"   Domain: {domain}")

                    # Extract button press details from attributes
                    attributes = new_state.get('attributes', {})
                    event_type = attributes.get('event_type', 'unknown')
                    logger.info(f"   Press Type: {event_type}")

                    return True
                else:
                    # Skip if no meaningful change
                    return False

            # Only process user-controlled devices that appear in logbook
            user_controlled_domains = [
                'light',              # Lights (user turns on/off)
                'switch',             # Switches (user controls)
                'cover',              # Covers (user opens/closes)
                'fan',                # Fans (user controls)
                'climate',            # Climate (user adjusts)
                'media_player',       # Media players (user controls)
                'lock',               # Locks (user locks/unlocks)
                'alarm_control_panel',  # Alarms (user arms/disarms)
                'button',             # Buttons (user presses)
                'event'               # Event entities (button presses)
            ]

            if domain not in user_controlled_domains:
                return False

            # Check if this is a meaningful state change (not just attribute updates)
            new_state_value = new_state.get('state')
            old_state_value = old_state.get('state')

            # Skip if state didn't actually change
            if new_state_value == old_state_value:
                return False

            # Skip unavailable/unknown states
            if new_state_value in ['unavailable', 'unknown'] or old_state_value in ['unavailable', 'unknown']:
                return False

            logger.info(
                f"🔘 USER DEVICE EVENT: {entity_id} {old_state_value} → {new_state_value}")
            return True

        # Skip all other events (sensors, updates, configuration changes, etc.)
        logger.debug(f"⏭️  Skipping non-logbook event: {event_type}")
        return False

    def format_event_data(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Format HA event data for Google Sheets with expanded analytics columns"""
        event_type = event.get('event_type', '')
        event_data = event.get('data', {})

        # Generate truly unique event ID with more entropy
        import uuid
        timestamp_ms = int(time.time() * 1000)
        event_hash = hash(str(event)) % 100000
        random_suffix = str(uuid.uuid4())[:8]
        event_id = f"evt_{timestamp_ms}_{event_hash}_{random_suffix}"

        # Base formatted data with expanded columns for dashboard analytics
        # IMPORTANT: Order must match Google Sheets columns exactly!
        formatted_data = {
            'event_id': event_id,
            'timestamp': event.get('time_fired', datetime.now(timezone.utc).isoformat()),
            'event_type': event_type,
            'entity_id': '',
            'domain': '',
            'service': '',
            'old_state': '',
            'new_state': '',
            'user_id': event.get('context', {}).get('user_id', ''),
            'source': 'home_assistant_logbook',
            'friendly_name': '',
            'device_class': '',
            # Columns after P (16) - these were missing!
            'device_id': '',
            'area_id': '',
            'area_name': '',
            'device_name': '',
            'platform': '',
            'operation_type': '',  # on, off, toggle, dim, brighten, etc.
            'operation_category': '',  # lighting, climate, security, etc.
            'interaction_type': '',  # manual, automation, schedule, etc.
            'day_of_week': '',
            'hour_of_day': '',
            'is_weekend': '',
            'time_period': '',  # morning, afternoon, evening, night
            'brightness': '',
            'color_temp': '',
            'rgb_color': '',
            'fan_speed': '',
            'temperature': '',
            'humidity': '',
            'battery_level': '',
            'signal_strength': '',
            'event_subtype': '',
            'button_type': '',
            'press_count': '',
            'automation_id': '',
            'automation_name': '',
            'scene_name': '',
            'manufacturer': '',
            'model': '',
            'sw_version': '',
            'attributes': ''
        }

        # Handle logbook entries specially
        if event_type == 'logbook_entry':
            logbook_data = event_data
            formatted_data.update({
                'entity_id': logbook_data.get('entity_id', ''),
                'domain': logbook_data.get('domain', ''),
                'new_state': logbook_data.get('message', ''),
                'attributes': json.dumps({
                    'name': logbook_data.get('name', ''),
                    'message': logbook_data.get('message', ''),
                    'icon': logbook_data.get('icon', ''),
                    'source': logbook_data.get('source', ''),
                    'context_id': logbook_data.get('context_id', ''),
                    'context_user_id': logbook_data.get('context_user_id', ''),
                    'when': logbook_data.get('when', 0)
                }),
                'source': 'logbook_stream'
            })
            return formatted_data

        if event_type == 'state_changed':
            entity_id = event_data.get('entity_id', '')
            formatted_data['entity_id'] = entity_id
            formatted_data['domain'] = entity_id.split(
                '.')[0] if entity_id else ''

            old_state = event_data.get('old_state', {})
            new_state = event_data.get('new_state', {})

            formatted_data['old_state'] = old_state.get(
                'state', '') if old_state else ''
            formatted_data['new_state'] = new_state.get(
                'state', '') if new_state else ''

            if self.include_attributes and new_state:
                attributes = new_state.get('attributes', {})
                # Remove large attributes to avoid size limits
                filtered_attrs = {k: v for k, v in attributes.items()
                                  if k not in ['entity_picture', 'icon', 'device_class'] and len(str(v)) < 100}
                formatted_data['attributes'] = json.dumps(
                    filtered_attrs) if filtered_attrs else ''

        elif event_type == 'service_called' or event_type == 'call_service':
            formatted_data['domain'] = event_data.get('domain', '')
            formatted_data['service'] = event_data.get('service', '')
            service_data = event_data.get('service_data', {})
            if service_data:
                formatted_data['attributes'] = json.dumps(service_data)

        elif event_type == 'automation_triggered':
            formatted_data['automation_id'] = event_data.get('name', '')
            formatted_data['entity_id'] = event_data.get('entity_id', '')

        elif event_type == 'script_started':
            formatted_data['automation_id'] = event_data.get('name', '')
            formatted_data['entity_id'] = event_data.get('entity_id', '')

        elif event_type == 'logbook_entry':
            formatted_data['entity_id'] = event_data.get('entity_id', '')
            formatted_data['domain'] = event_data.get('domain', '')
            formatted_data['new_state'] = event_data.get('message', '')
            formatted_data['attributes'] = json.dumps({
                'name': event_data.get('name', ''),
                'message': event_data.get('message', '')
            })

        elif 'device' in event_type.lower() or 'button' in event_type.lower() or 'matter' in event_type.lower():
            # Handle device automation events (Matter devices, buttons, etc.)
            formatted_data['device_id'] = event_data.get('device_id', '')
            formatted_data['entity_id'] = event_data.get('entity_id', '')
            formatted_data['platform'] = event_data.get('platform', '')
            formatted_data['new_state'] = 'button_pressed' if 'button' in event_type.lower(
            ) else 'device_event'

            # Store all event data as attributes for device events
            filtered_data = {k: v for k,
                             v in event_data.items() if len(str(v)) < 200}
            formatted_data['attributes'] = json.dumps(
                filtered_data) if filtered_data else ''

        else:
            # Handle any other custom events - capture everything!
            formatted_data['attributes'] = json.dumps(
                event_data) if event_data else ''

            # Try to extract entity_id from various possible locations
            if 'entity_id' in event_data:
                formatted_data['entity_id'] = event_data['entity_id']
            elif 'device_id' in event_data:
                formatted_data['device_id'] = event_data['device_id']

        # Extract detailed attributes for dashboard analytics
        self.extract_dashboard_attributes(
            formatted_data, event_type, event_data)

        return formatted_data

    def extract_dashboard_attributes(self, formatted_data: Dict[str, Any], event_type: str, event_data: Dict[str, Any]):
        """Extract detailed attributes for dashboard analytics"""
        try:
            # Parse timestamp for time-based analytics (convert to IST for analysis)
            timestamp_str = formatted_data.get('timestamp', '')
            if timestamp_str:
                # Parse UTC timestamp
                utc_timestamp = datetime.fromisoformat(
                    timestamp_str.replace('Z', '+00:00'))

                # Convert to local timezone for analytics (default IST UTC+5:30)
                hours = int(self.timezone_offset)
                minutes = int((self.timezone_offset - hours) * 60)
                local_offset = timedelta(hours=hours, minutes=minutes)
                local_timestamp = utc_timestamp + local_offset

                formatted_data.update({
                    'day_of_week': local_timestamp.strftime('%A'),
                    'hour_of_day': str(local_timestamp.hour),
                    'is_weekend': 'Yes' if local_timestamp.weekday() >= 5 else 'No',
                    'time_period': self.get_time_period(local_timestamp.hour)
                })

            # Extract attributes from JSON if available
            attributes_json = formatted_data.get('attributes', '{}')
            if attributes_json:
                try:
                    attributes = json.loads(attributes_json)

                    # Extract common attributes
                    formatted_data['friendly_name'] = attributes.get(
                        'friendly_name', '')
                    formatted_data['device_class'] = attributes.get(
                        'device_class', '')

                    # Extract lighting attributes
                    if 'brightness' in attributes:
                        formatted_data['brightness'] = str(
                            attributes.get('brightness', ''))
                    if 'color_temp' in attributes:
                        formatted_data['color_temp'] = str(
                            attributes.get('color_temp', ''))
                    if 'rgb_color' in attributes:
                        formatted_data['rgb_color'] = str(
                            attributes.get('rgb_color', ''))

                    # Extract climate attributes
                    if 'temperature' in attributes:
                        formatted_data['temperature'] = str(
                            attributes.get('temperature', ''))
                    if 'humidity' in attributes:
                        formatted_data['humidity'] = str(
                            attributes.get('humidity', ''))

                    # Extract device attributes
                    if 'battery_level' in attributes:
                        formatted_data['battery_level'] = str(
                            attributes.get('battery_level', ''))
                    if 'signal_strength' in attributes:
                        formatted_data['signal_strength'] = str(
                            attributes.get('signal_strength', ''))

                    # Extract button/event attributes
                    if 'event_type' in attributes:
                        formatted_data['event_subtype'] = attributes.get(
                            'event_type', '')
                        formatted_data['button_type'] = attributes.get(
                            'event_type', '')
                    if 'totalNumberOfPressesCounted' in attributes:
                        formatted_data['press_count'] = str(
                            attributes.get('totalNumberOfPressesCounted', ''))

                    # Extract device info
                    formatted_data['manufacturer'] = attributes.get(
                        'manufacturer', '')
                    formatted_data['model'] = attributes.get('model', '')
                    formatted_data['sw_version'] = attributes.get(
                        'sw_version', '')

                except json.JSONDecodeError:
                    pass

            # Categorize operation and interaction types
            self.categorize_operation_type(
                formatted_data, event_type, event_data)

        except Exception as e:
            logger.debug(f"Error extracting dashboard attributes: {e}")

    def get_time_period(self, hour: int) -> str:
        """Get time period based on hour"""
        if 5 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 17:
            return 'afternoon'
        elif 17 <= hour < 21:
            return 'evening'
        else:
            return 'night'

    def categorize_operation_type(self, formatted_data: Dict[str, Any], event_type: str, event_data: Dict[str, Any]):
        """Categorize operation and interaction types for analytics"""
        domain = formatted_data.get('domain', '')
        service = formatted_data.get('service', '')
        old_state = formatted_data.get('old_state', '')
        new_state = formatted_data.get('new_state', '')
        entity_id = formatted_data.get('entity_id', '')

        # Determine operation type
        if event_type == 'state_changed':
            if old_state and new_state:
                if old_state == 'off' and new_state == 'on':
                    formatted_data['operation_type'] = 'turn_on'
                elif old_state == 'on' and new_state == 'off':
                    formatted_data['operation_type'] = 'turn_off'
                elif old_state != new_state:
                    formatted_data['operation_type'] = 'state_change'
                else:
                    formatted_data['operation_type'] = 'attribute_change'
        elif event_type == 'call_service':
            formatted_data['operation_type'] = service
        elif event_type == 'automation_triggered':
            formatted_data['operation_type'] = 'automation'
        elif 'button' in event_type.lower() or 'event' in domain:
            formatted_data['operation_type'] = 'button_press'

        # Determine operation category
        if domain == 'light':
            formatted_data['operation_category'] = 'lighting'
        elif domain in ['switch', 'outlet']:
            formatted_data['operation_category'] = 'power_control'
        elif domain in ['fan', 'climate']:
            formatted_data['operation_category'] = 'climate_control'
        elif domain in ['cover', 'blind', 'curtain']:
            formatted_data['operation_category'] = 'window_covering'
        elif domain in ['lock', 'alarm_control_panel']:
            formatted_data['operation_category'] = 'security'
        elif domain in ['media_player', 'remote']:
            formatted_data['operation_category'] = 'entertainment'
        elif domain in ['button', 'event'] or 'button' in entity_id:
            formatted_data['operation_category'] = 'button_control'
        elif domain == 'automation':
            formatted_data['operation_category'] = 'automation'
        elif domain == 'scene':
            formatted_data['operation_category'] = 'scene_control'
        else:
            formatted_data['operation_category'] = 'other'

        # Determine interaction type
        user_id = formatted_data.get('user_id', '')
        automation_id = formatted_data.get('automation_id', '')

        if user_id:
            formatted_data['interaction_type'] = 'manual'
        elif automation_id or event_type == 'automation_triggered':
            formatted_data['interaction_type'] = 'automation'
        elif 'button' in event_type.lower() or domain == 'event':
            formatted_data['interaction_type'] = 'physical_button'
        elif event_type == 'call_service':
            formatted_data['interaction_type'] = 'service_call'
        else:
            formatted_data['interaction_type'] = 'system'

    async def process_event(self, event: Dict[str, Any]):
        """Process a single HA event"""
        try:
            event_type = event.get('event_type', '')
            self.stats['events_received'] += 1

            # Log all events for debugging
            logger.info(f"🔍 Processing: {event_type}")
            if logger.level == logging.DEBUG:
                logger.debug(
                    f"Event details: {event_type} - Data: {event.get('data', {})}")

            # Check for duplicate events first
            if self.is_duplicate_event(event):
                self.stats['events_filtered'] += 1
                logger.debug(f"🔄 Duplicate event skipped: {event_type}")
                return

            if not self.should_process_event(event):
                self.stats['events_filtered'] += 1
                logger.info(f"⏭️  Filtered out: {event_type}")
                return

            self.stats['events_processed'] += 1
            self.stats['last_event_time'] = datetime.now(
                timezone.utc).isoformat()

            formatted_data = self.format_event_data(event)

            # Check if we've already processed this exact event
            event_id = formatted_data.get('event_id', '')
            if event_id in self.processed_events:
                logger.debug(f"🔄 Event already processed: {event_id}")
                return

            # Mark as processed
            self.processed_events.add(event_id)

            # Clean up old processed events (keep last 1000)
            if len(self.processed_events) > 1000:
                # Remove oldest 200 events
                old_events = list(self.processed_events)[:200]
                for old_event in old_events:
                    self.processed_events.discard(old_event)

            # Send to Google Sheets
            success = await self.send_to_google_sheets(formatted_data)

            if success:
                logger.info(
                    f"✅ Sent to Sheets: {event_type} - {formatted_data.get('entity_id', formatted_data.get('device_id', 'N/A'))}")
            else:
                logger.warning(
                    f"❌ Failed to send: {formatted_data.get('event_id')}")

        except Exception as e:
            logger.error(f"💥 Error processing event: {e}")
            self.stats['errors'] += 1

    async def poll_logbook_events(self):
        """Poll Home Assistant logbook for events (avoids WebSocket conflicts)"""
        last_check_time = datetime.now(timezone.utc)

        while True:
            try:
                logger.info("🔍 Polling logbook for new events...")

                # Get events from the last 5 minutes
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(minutes=5)

                headers = self.get_auth_headers()

                # Use logbook API to get all events
                # Format timestamp properly for HA API
                start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S%z')
                logbook_url = f"{self.ha_url}/api/logbook/{start_time_str}"

                logger.debug(f"Requesting logbook: {logbook_url}")

                response = requests.get(
                    logbook_url, headers=headers, timeout=30)

                logger.info(f"Logbook API response: {response.status_code}")

                if response.status_code == 200:
                    logbook_entries = response.json()
                    logger.info(
                        f"📋 Found {len(logbook_entries)} logbook entries")

                    if logger.level == logging.DEBUG:
                        # Show first 3 entries
                        logger.debug(f"Logbook entries: {logbook_entries[:3]}")

                    new_events = 0

                    for entry in logbook_entries:
                        try:
                            entry_time_str = entry.get('when', '')
                            if not entry_time_str:
                                continue

                            # Parse the timestamp properly
                            entry_time = datetime.fromisoformat(
                                entry_time_str.replace('Z', '+00:00'))

                            # Only process events newer than our last check
                            if entry_time > last_check_time:
                                # Convert logbook entry to event format
                                event = {
                                    'event_type': 'logbook_entry',
                                    'time_fired': entry.get('when'),
                                    'data': {
                                        'entity_id': entry.get('entity_id', ''),
                                        'name': entry.get('name', ''),
                                        'message': entry.get('message', ''),
                                        'domain': entry.get('domain', ''),
                                        'context_id': entry.get('context_id', ''),
                                        'context_user_id': entry.get('context_user_id', ''),
                                        'source': 'logbook'
                                    },
                                    'context': {
                                        'id': entry.get('context_id', ''),
                                        'user_id': entry.get('context_user_id', '')
                                    }
                                }

                                # Check if this is a button or device event
                                entry_name = entry.get('name', '').lower()
                                entry_message = entry.get(
                                    'message', '').lower()
                                entity_id = entry.get('entity_id', '').lower()

                                is_button_event = (
                                    'button' in entry_name or
                                    'button' in entry_message or
                                    'button' in entity_id or
                                    'arre' in entry_name or
                                    'arre' in entity_id or
                                    'pressed' in entry_message or
                                    'clicked' in entry_message or
                                    'detected an event' in entry_message
                                )

                                if is_button_event:
                                    logger.info(
                                        f"🔘 BUTTON LOGBOOK EVENT: {entry.get('name', 'Unknown')} - {entry.get('message', 'No message')}")
                                else:
                                    logger.info(
                                        f"🔍 Processing logbook entry: {entry.get('name', 'Unknown')} - {entry.get('message', 'No message')}")

                                await self.process_event(event)
                                new_events += 1
                        except Exception as e:
                            logger.error(
                                f"Error processing logbook entry: {e}")
                            logger.debug(f"Problematic entry: {entry}")

                    if new_events > 0:
                        logger.info(
                            f"📊 Processed {new_events} new logbook events")
                    else:
                        logger.info("📊 No new logbook events found")

                    last_check_time = end_time

                else:
                    logger.error(
                        f"Failed to get logbook: {response.status_code} - {response.text}")

                    # Try a simple API test
                    test_url = f"{self.ha_url}/api/"
                    test_response = requests.get(
                        test_url, headers=headers, timeout=10)
                    logger.info(
                        f"API test: {test_response.status_code} - {test_response.text if test_response.status_code == 200 else 'Failed'}")

                # Also check for state changes via states API
                await self._check_state_changes()

                # Wait before next poll - more frequent for button events
                # Poll every 10 seconds for faster button detection
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error polling logbook: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _check_state_changes(self):
        """Check for state changes via REST API"""
        try:
            headers = self.get_auth_headers()

            # Get current states
            response = requests.get(
                f"{self.ha_url}/api/states", headers=headers, timeout=30)

            if response.status_code == 200:
                current_states = response.json()

                # Store states for comparison (simple implementation)
                if not hasattr(self, '_last_states'):
                    self._last_states = {}

                for state in current_states:
                    entity_id = state.get('entity_id')
                    current_state = state.get('state')
                    last_changed = state.get('last_changed')

                    if entity_id and entity_id in self._last_states:
                        old_state_data = self._last_states[entity_id]

                        # Check if state changed
                        if (old_state_data.get('state') != current_state or
                                old_state_data.get('last_changed') != last_changed):

                            # Create state_changed event
                            event = {
                                'event_type': 'state_changed',
                                'time_fired': last_changed,
                                'data': {
                                    'entity_id': entity_id,
                                    'new_state': state,
                                    'old_state': old_state_data
                                },
                                'context': state.get('context', {})
                            }

                            await self.process_event(event)

                    # Update stored state
                    self._last_states[entity_id] = state

        except Exception as e:
            logger.error(f"Error checking state changes: {e}")

    async def test_api_connectivity(self):
        """Test basic API connectivity"""
        try:
            headers = self.get_auth_headers()

            # Test basic API
            logger.info("🔍 Testing Home Assistant API connectivity...")
            response = requests.get(
                f"{self.ha_url}/api/", headers=headers, timeout=10)

            if response.status_code == 200:
                logger.info("✅ API connectivity test passed")
                api_response = response.json()
                logger.info(f"API Response: {api_response}")
            else:
                logger.error(
                    f"❌ API test failed: {response.status_code} - {response.text}")
                return False

            # Test states endpoint
            logger.info("🔍 Testing states endpoint...")
            response = requests.get(
                f"{self.ha_url}/api/states", headers=headers, timeout=10)

            if response.status_code == 200:
                states = response.json()
                logger.info(
                    f"✅ States endpoint working - found {len(states)} entities")

                # Look for your button specifically
                button_entities = [s for s in states if 'button' in s.get(
                    'entity_id', '').lower() or 'arre' in s.get('entity_id', '').lower()]
                if button_entities:
                    logger.info(
                        f"🔘 Found button entities: {[e['entity_id'] for e in button_entities]}")
                else:
                    logger.warning("⚠️  No button entities found")
            else:
                logger.error(f"❌ States test failed: {response.status_code}")

            # Test logbook endpoint
            logger.info("🔍 Testing logbook endpoint...")
            from datetime import timedelta
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S%z')

            response = requests.get(
                f"{self.ha_url}/api/logbook/{start_time_str}", headers=headers, timeout=10)

            if response.status_code == 200:
                logbook = response.json()
                logger.info(
                    f"✅ Logbook endpoint working - found {len(logbook)} entries")

                # Look for button events
                button_events = [e for e in logbook if 'button' in e.get(
                    'name', '').lower() or 'arre' in e.get('name', '').lower()]
                if button_events:
                    logger.info(
                        f"🔘 Found button events in logbook: {len(button_events)}")
                    logger.info(
                        f"Latest button event: {button_events[0] if button_events else 'None'}")
            else:
                logger.error(f"❌ Logbook test failed: {response.status_code}")

            return True

        except Exception as e:
            logger.error(f"❌ API connectivity test failed: {e}")
            return False

    async def listen_to_logbook_stream(self):
        """Listen to Home Assistant logbook stream using proper API"""
        import websockets

        while True:
            try:
                logger.info(
                    "🔗 Connecting to Home Assistant WebSocket for LOGBOOK STREAM...")

                async with websockets.connect(self.websocket_url) as websocket:
                    # Authenticate
                    auth_msg = {
                        "type": "auth",
                        "access_token": self.ha_token
                    }
                    await websocket.send(json.dumps(auth_msg))

                    # Wait for auth response - handle auth_required first
                    auth_response = await websocket.recv()
                    auth_data = json.loads(auth_response)

                    if auth_data.get('type') == 'auth_required':
                        logger.info(
                            f"🔑 Auth required, HA version: {auth_data.get('ha_version')}")
                        # Wait for the actual auth result
                        auth_response = await websocket.recv()
                        auth_data = json.loads(auth_response)

                    if auth_data.get('type') != 'auth_ok':
                        logger.error(
                            f"❌ WebSocket authentication failed: {auth_data}")
                        return

                    logger.info("✅ WebSocket authenticated for logbook stream")

                    # Subscribe to events that generate logbook entries
                    # Use standard WebSocket API (logbook/event_stream doesn't exist)
                    subscribe_msg = {
                        "id": 1,
                        "type": "subscribe_events"
                        # No event_type = ALL events (we'll filter in should_process_event)
                    }
                    await websocket.send(json.dumps(subscribe_msg))

                    # Wait for subscription confirmation
                    sub_response = await websocket.recv()
                    sub_data = json.loads(sub_response)

                    if sub_data.get('success'):
                        logger.info(
                            "📋 Subscribed to ALL events for logbook filtering")
                        logger.info(
                            "🔘 Will capture: Button presses, device automation, user actions")
                        logger.info(
                            "⏭️  Will filter: Sensors, updates, configuration changes")
                    else:
                        logger.error(
                            f"❌ Failed to subscribe to events: {sub_data}")
                        return

                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            # Handle event messages
                            if data.get('type') == 'event' and data.get('id') == 1:
                                event = data.get('event', {})

                                # Process the event through our logbook filter
                                if self.should_process_event(event):
                                    await self.process_event(event)

                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON received: {message}")
                        except Exception as e:
                            logger.error(
                                f"Error handling WebSocket message: {e}")

            except Exception as e:
                logger.error(f"Logbook WebSocket connection error: {e}")
                await asyncio.sleep(5)
                logger.info("🔄 Retrying logbook WebSocket connection...")

    async def listen_to_websocket_simple(self):
        """Simple WebSocket listener that subscribes to ALL events"""
        import websockets

        while True:
            try:
                logger.info("🔌 Connecting to Home Assistant WebSocket...")

                async with websockets.connect(self.websocket_url) as websocket:
                    # For WebSocket authentication, ALWAYS use HA token (not supervisor token)
                    # Supervisor token is for internal operations, HA token is for WebSocket
                    token_to_use = self.ha_token
                    auth_msg = {
                        "type": "auth",
                        "access_token": token_to_use
                    }

                    logger.info(
                        f"🔑 Using HA token for WebSocket authentication")
                    logger.info(
                        f"🔑 Token starts with: {token_to_use[:20]}..." if token_to_use else "🔑 No token available")
                    await websocket.send(json.dumps(auth_msg))

                    # Wait for auth response
                    auth_response = await websocket.recv()
                    auth_data = json.loads(auth_response)

                    if auth_data.get('type') != 'auth_ok':
                        logger.error(
                            f"❌ WebSocket authentication failed: {auth_data}")
                        raise Exception("Authentication failed")

                    logger.info("✅ WebSocket authenticated successfully")

                    # Subscribe to specific event types for comprehensive monitoring
                    subscribe_msg = {
                        "id": 1,
                        "type": "subscribe_events"
                        # Subscribe to ALL events to capture everything
                    }
                    await websocket.send(json.dumps(subscribe_msg))

                    # Wait for subscription confirmation
                    sub_response = await websocket.recv()
                    sub_data = json.loads(sub_response)

                    if sub_data.get('success'):
                        logger.info("✅ Successfully subscribed to ALL events")
                    else:
                        logger.error(f"❌ Failed to subscribe: {sub_data}")
                        raise Exception("Subscription failed")

                    # Listen for events
                    logger.info("🎧 Listening for ALL WebSocket events...")
                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            if data.get('type') == 'event':
                                event = data.get('event', {})
                                event_type = event.get('event_type', 'unknown')

                                logger.info(f"📨 WebSocket event: {event_type}")

                                # Log specific event types for debugging
                                if event_type in ['device_automation', 'zha_event', 'deconz_event', 'matter_event']:
                                    logger.info(
                                        f"🔘 DEVICE EVENT DETECTED: {event_type} - {event}")
                                elif 'button' in str(event).lower() or 'arre' in str(event).lower():
                                    logger.info(
                                        f"🔘 BUTTON EVENT DETECTED: {event}")
                                elif event_type == 'logbook_entry':
                                    logger.info(f"📋 LOGBOOK EVENT: {event}")
                                elif event_type == 'call_service':
                                    service_data = event.get('data', {})
                                    if 'button' in str(service_data).lower():
                                        logger.info(
                                            f"🔘 BUTTON SERVICE CALL: {event}")

                                await self.process_event(event)

                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON received: {message}")
                        except Exception as e:
                            logger.error(f"Error handling message: {e}")

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(10)
                raise  # Re-raise to trigger fallback

    async def collect_historical_data(self):
        """Collect historical data from Home Assistant"""
        if not self.collect_historical:
            logger.info("Historical data collection disabled")
            return

        logger.info("Starting historical data collection...")

        try:
            headers = self.get_auth_headers()

            # First, get current states
            await self._collect_current_states(headers)

            # Then, get historical events from the database
            await self._collect_historical_events(headers)

        except Exception as e:
            logger.error(f"Error collecting historical data: {e}")

    async def _collect_current_states(self, headers):
        """Collect current states from Home Assistant"""
        try:
            response = requests.get(
                f"{self.ha_url}/api/states", headers=headers, timeout=30)

            if response.status_code == 200:
                states = response.json()
                logger.info(f"Found {len(states)} current states")

                for state in states:
                    if not self.should_process_state(state):
                        continue

                    # Create a state_changed event from current state
                    event = {
                        'event_type': 'state_changed',
                        'time_fired': state.get('last_changed', datetime.now(timezone.utc).isoformat()),
                        'data': {
                            'entity_id': state.get('entity_id'),
                            'new_state': state,
                            'old_state': None
                        },
                        'context': state.get('context', {})
                    }

                    await self.process_event(event)

                logger.info("Current states collection completed")
            else:
                logger.error(f"Failed to get states: {response.status_code}")

        except Exception as e:
            logger.error(f"Error collecting current states: {e}")

    async def _collect_historical_events(self, headers):
        """Collect historical events from Home Assistant database"""
        try:
            # Get events from the last 30 days
            from datetime import timedelta
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=30)

            # Use the history API to get historical data
            history_url = f"{self.ha_url}/api/history/period/{start_time.isoformat()}"

            logger.info(
                f"Collecting historical events from {start_time.isoformat()} to {end_time.isoformat()}")

            response = requests.get(history_url, headers=headers, timeout=60)

            if response.status_code == 200:
                history_data = response.json()
                total_events = 0

                for entity_history in history_data:
                    if not entity_history:
                        continue

                    entity_id = entity_history[0].get(
                        'entity_id') if entity_history else None
                    if not entity_id or not self.should_process_entity_id(entity_id):
                        continue

                    # Process each state change in the history
                    for i, state in enumerate(entity_history):
                        if i == 0:
                            continue  # Skip first state as it has no previous state

                        old_state = entity_history[i-1]
                        new_state = state

                        # Create historical state_changed event
                        event = {
                            'event_type': 'state_changed',
                            'time_fired': new_state.get('last_changed', new_state.get('last_updated')),
                            'data': {
                                'entity_id': entity_id,
                                'new_state': new_state,
                                'old_state': old_state
                            },
                            'context': new_state.get('context', {}),
                            'origin': 'historical'
                        }

                        await self.process_event(event)
                        total_events += 1

                        # Add small delay to prevent overwhelming the system
                        if total_events % 100 == 0:
                            await asyncio.sleep(0.1)
                            logger.info(
                                f"Processed {total_events} historical events...")

                logger.info(
                    f"Historical events collection completed. Processed {total_events} events")
            else:
                logger.error(
                    f"Failed to get historical data: {response.status_code}")

        except Exception as e:
            logger.error(f"Error collecting historical events: {e}")

    def should_process_entity_id(self, entity_id: str) -> bool:
        """Check if entity_id should be processed"""
        if not entity_id:
            return False

        domain = entity_id.split('.')[0]

        if domain in self.excluded_domains:
            return False

        if entity_id in self.excluded_entities:
            return False

        return True

    def should_process_state(self, state: Dict[str, Any]) -> bool:
        """Check if state should be processed"""
        entity_id = state.get('entity_id', '')
        if not entity_id:
            return False

        domain = entity_id.split('.')[0]

        if domain in self.excluded_domains:
            return False

        if entity_id in self.excluded_entities:
            return False

        return True


# Flask web interface
app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html', stats=collector.stats)


@app.route('/api/stats')
def api_stats():
    return jsonify(collector.stats)


@app.route('/api/test')
def api_test():
    """Test Google Sheets connection"""
    test_data = {
        'event_id': 'test_' + str(int(time.time())),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event_type': 'test_event',
        'entity_id': 'test.entity',
        'domain': 'test',
        'service': '',
        'old_state': '',
        'new_state': 'test',
        'attributes': '{"test": true}',
        'user_id': 'test_user',
        'source': 'addon_test',
        'automation_id': '',
        'device_id': '',
        'area_id': '',
        'platform': ''
    }

    try:
        response = requests.post(
            collector.google_sheets_url,
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        return jsonify({
            'success': response.status_code == 200,
            'status_code': response.status_code,
            'response': response.json() if response.status_code == 200 else response.text
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


def run_flask():
    """Run Flask web interface"""
    app.run(host='0.0.0.0', port=8099, debug=False)


async def main():
    """Main function"""
    global collector
    collector = HomeAssistantDataCollector()

    logger.info("🚀 Starting Home Assistant Data Collector")
    logger.info("📝 Real-time Home Assistant event monitoring")

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Test API connectivity first
    await collector.test_api_connectivity()

    # Collect historical data first
    await collector.collect_historical_data()

    # Start WebSocket monitoring with proper logbook filtering
    logger.info("🔄 Starting WebSocket monitoring with LOGBOOK FILTERING...")
    logger.info("📋 Using standard WebSocket API with smart filtering")
    logger.info("🔘 Will capture: ONLY events that appear in HA logbook")

    # Use WebSocket with logbook filtering
    await collector.listen_to_logbook_stream()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
