#!/usr/bin/env python3
"""
Custom Data Storage Add-on for Home Assistant
Provides REST API and WebSocket interface for storing custom values
"""

import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import eventlet

# Monkey patch for eventlet
eventlet.monkey_patch()

# Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'info').upper()
STORAGE_PATH = os.getenv('STORAGE_PATH', '/data/custom_storage')
MAX_STORAGE_SIZE_MB = int(os.getenv('MAX_STORAGE_SIZE_MB', '100'))
ENABLE_WEBSOCKET = os.getenv('ENABLE_WEBSOCKET', 'true').lower() == 'true'
ENABLE_CORS = os.getenv('ENABLE_CORS', 'true').lower() == 'true'
API_KEY = os.getenv('API_KEY', '')

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'custom_data_storage_secret_key'

# Enable CORS if configured
if ENABLE_CORS:
    CORS(app, origins="*")

# Initialize SocketIO if enabled
if ENABLE_WEBSOCKET:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
else:
    socketio = None

class CustomDataStorage:
    """Custom data storage manager"""
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.data_file = self.storage_path / 'custom_data.json'
        self.metadata_file = self.storage_path / 'metadata.json'
        self.load_data()
        
    def load_data(self):
        """Load data from storage"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    self.data = json.load(f)
            else:
                self.data = {}
                
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = {
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'last_updated': datetime.now(timezone.utc).isoformat(),
                    'total_keys': 0,
                    'total_updates': 0
                }
                
            logger.info(f"Loaded {len(self.data)} custom data entries")
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.data = {}
            self.metadata = {
                'created_at': datetime.now(timezone.utc).isoformat(),
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'total_keys': 0,
                'total_updates': 0
            }
    
    def save_data(self):
        """Save data to storage"""
        try:
            # Check storage size
            if self._get_storage_size_mb() > MAX_STORAGE_SIZE_MB:
                raise Exception(f"Storage size exceeds {MAX_STORAGE_SIZE_MB}MB limit")
            
            # Update metadata
            self.metadata['last_updated'] = datetime.now(timezone.utc).isoformat()
            self.metadata['total_keys'] = len(self.data)
            self.metadata['total_updates'] += 1
            
            # Save data
            with open(self.data_file, 'w') as f:
                json.dump(self.data, f, indent=2)
                
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
                
            logger.debug("Data saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            raise
    
    def _get_storage_size_mb(self) -> float:
        """Get current storage size in MB"""
        total_size = 0
        for file_path in self.storage_path.glob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)
    
    def set_value(self, key: str, value: Any, category: str = 'default') -> Dict[str, Any]:
        """Set a custom value"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create nested structure if needed
        if category not in self.data:
            self.data[category] = {}
        
        # Store value with metadata
        self.data[category][key] = {
            'value': value,
            'timestamp': timestamp,
            'type': type(value).__name__
        }
        
        self.save_data()
        
        # Emit WebSocket event if enabled
        if socketio:
            socketio.emit('data_updated', {
                'action': 'set',
                'category': category,
                'key': key,
                'value': value,
                'timestamp': timestamp
            })
        
        logger.info(f"Set value: {category}.{key} = {value}")
        
        return {
            'success': True,
            'category': category,
            'key': key,
            'value': value,
            'timestamp': timestamp
        }
    
    def get_value(self, key: str, category: str = 'default') -> Optional[Any]:
        """Get a custom value"""
        try:
            if category in self.data and key in self.data[category]:
                return self.data[category][key]['value']
            return None
        except Exception as e:
            logger.error(f"Error getting value {category}.{key}: {e}")
            return None
    
    def get_all_values(self, category: str = None) -> Dict[str, Any]:
        """Get all values or values in a specific category"""
        if category:
            return self.data.get(category, {})
        return self.data
    
    def delete_value(self, key: str, category: str = 'default') -> bool:
        """Delete a custom value"""
        try:
            if category in self.data and key in self.data[category]:
                del self.data[category][key]
                
                # Remove empty categories
                if not self.data[category]:
                    del self.data[category]
                
                self.save_data()
                
                # Emit WebSocket event if enabled
                if socketio:
                    socketio.emit('data_updated', {
                        'action': 'delete',
                        'category': category,
                        'key': key,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
                
                logger.info(f"Deleted value: {category}.{key}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting value {category}.{key}: {e}")
            return False
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get storage metadata"""
        return {
            **self.metadata,
            'storage_size_mb': round(self._get_storage_size_mb(), 2),
            'max_storage_size_mb': MAX_STORAGE_SIZE_MB,
            'categories': list(self.data.keys()),
            'total_values': sum(len(category_data) for category_data in self.data.values())
        }

# Initialize storage
storage = CustomDataStorage(STORAGE_PATH)

def check_api_key():
    """Check API key if configured"""
    if API_KEY:
        provided_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if provided_key != API_KEY:
            return False
    return True

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'storage_size_mb': round(storage._get_storage_size_mb(), 2),
        'websocket_enabled': ENABLE_WEBSOCKET
    })

@app.route('/api/data', methods=['POST'])
def set_data():
    """Set custom data"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        key = data.get('key')
        value = data.get('value')
        category = data.get('category', 'default')
        
        if not key:
            return jsonify({'error': 'Key is required'}), 400
        
        result = storage.set_value(key, value, category)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error setting data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/<category>/<key>', methods=['GET'])
def get_data(category, key):
    """Get specific custom data"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        value = storage.get_value(key, category)
        if value is not None:
            return jsonify({
                'success': True,
                'category': category,
                'key': key,
                'value': value
            })
        else:
            return jsonify({'error': 'Key not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data', methods=['GET'])
@app.route('/api/data/<category>', methods=['GET'])
def get_all_data(category=None):
    """Get all custom data or data in a specific category"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        data = storage.get_all_values(category)
        return jsonify({
            'success': True,
            'category': category,
            'data': data
        })
        
    except Exception as e:
        logger.error(f"Error getting all data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/<category>/<key>', methods=['DELETE'])
def delete_data(category, key):
    """Delete specific custom data"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        success = storage.delete_value(key, category)
        if success:
            return jsonify({
                'success': True,
                'message': f'Deleted {category}.{key}'
            })
        else:
            return jsonify({'error': 'Key not found'}), 404
            
    except Exception as e:
        logger.error(f"Error deleting data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/metadata', methods=['GET'])
def get_metadata():
    """Get storage metadata"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        metadata = storage.get_metadata()
        return jsonify(metadata)
        
    except Exception as e:
        logger.error(f"Error getting metadata: {e}")
        return jsonify({'error': str(e)}), 500

# WebSocket events
if socketio:
    @socketio.on('connect')
    def handle_connect():
        """Handle WebSocket connection"""
        logger.info(f"Client connected: {request.sid}")
        emit('connected', {'message': 'Connected to Custom Data Storage'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle WebSocket disconnection"""
        logger.info(f"Client disconnected: {request.sid}")
    
    @socketio.on('get_data')
    def handle_get_data(data):
        """Handle WebSocket data request"""
        try:
            category = data.get('category')
            key = data.get('key')
            
            if key and category:
                value = storage.get_value(key, category)
                emit('data_response', {
                    'category': category,
                    'key': key,
                    'value': value,
                    'found': value is not None
                })
            else:
                all_data = storage.get_all_values(category)
                emit('data_response', {
                    'category': category,
                    'data': all_data
                })
                
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            emit('error', {'message': str(e)})

if __name__ == '__main__':
    logger.info("Starting Custom Data Storage Add-on")
    logger.info(f"Storage path: {STORAGE_PATH}")
    logger.info(f"WebSocket enabled: {ENABLE_WEBSOCKET}")
    logger.info(f"CORS enabled: {ENABLE_CORS}")
    
    if socketio:
        socketio.run(app, host='0.0.0.0', port=8100, debug=(LOG_LEVEL == 'DEBUG'))
    else:
        app.run(host='0.0.0.0', port=8100, debug=(LOG_LEVEL == 'DEBUG'))
