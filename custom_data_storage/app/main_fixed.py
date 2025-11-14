#!/usr/bin/env python3
"""
SQLite Custom Data Storage Add-on for Home Assistant
Professional database storage for large-scale data management
"""

# IMPORTANT: Monkey patch MUST be first, before any other imports
import eventlet
eventlet.monkey_patch()

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

# Import storage backends
from database_storage import DatabaseStorage

# Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'info').upper()
STORAGE_PATH = os.getenv('STORAGE_PATH', '/data/custom_storage')
MAX_STORAGE_SIZE_MB = int(os.getenv('MAX_STORAGE_SIZE_MB', '2000'))
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
app.config['SECRET_KEY'] = 'custom_data_storage_enhanced_secret_key'

# Enable CORS if configured
if ENABLE_CORS:
    CORS(app, origins="*")

# Initialize SocketIO if enabled
if ENABLE_WEBSOCKET:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
else:
    socketio = None

class StorageManager:
    """SQLite storage manager for professional data management"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.storage_type = 'sqlite'

        self.backend = DatabaseStorage(storage_path)
        logger.info("Using SQLite storage backend for scalable data management")

    def set_value(self, key: str, value: Any, category: str = 'default') -> Dict[str, Any]:
        """Set a custom value"""
        result = self.backend.set_value(key, value, category)
        
        # Emit WebSocket event if enabled
        if socketio and result.get('success'):
            socketio.emit('data_updated', {
                'action': 'set',
                'category': category,
                'key': key,
                'value': value,
                'timestamp': result.get('timestamp')
            })
        
        return result
    
    def get_value(self, key: str, category: str = 'default') -> Optional[Any]:
        """Get a custom value"""
        return self.backend.get_value(key, category)
    
    def get_all_values(self, category: str = None) -> Dict[str, Any]:
        """Get all values or values in a specific category"""
        return self.backend.get_all_values(category)
    
    def delete_value(self, key: str, category: str = 'default') -> bool:
        """Delete a custom value"""
        success = self.backend.delete_value(key, category)
        
        # Emit WebSocket event if enabled
        if socketio and success:
            socketio.emit('data_updated', {
                'action': 'delete',
                'category': category,
                'key': key,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return success
    
    def search_values(self, search_term: str, category: str = None):
        """Search for values using SQLite"""
        return self.backend.search_values(search_term, category)
    
    def get_categories(self):
        """Get list of categories"""
        return self.backend.get_categories()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get storage metadata"""
        metadata = self.backend.get_metadata()
        metadata['storage_type'] = self.storage_type
        metadata['max_storage_size_mb'] = MAX_STORAGE_SIZE_MB
        return metadata
    
    def optimize_storage(self):
        """Optimize SQLite storage"""
        self.backend.vacuum_database()
    
    def backup_storage(self, backup_path: str) -> bool:
        """Backup SQLite storage"""
        return self.backend.backup_database(backup_path)

# Initialize storage
storage = StorageManager(STORAGE_PATH)

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
    metadata = storage.get_metadata()
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'storage_type': 'sqlite',
        'storage_size_mb': metadata.get('database_size_mb', 0),
        'total_values': metadata.get('total_values', 0),
        'total_categories': metadata.get('total_categories', 0),
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

@app.route('/api/search', methods=['GET'])
def search_data():
    """Search for data"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        search_term = request.args.get('q', '')
        category = request.args.get('category')
        
        if not search_term:
            return jsonify({'error': 'Search term required'}), 400
        
        results = storage.search_values(search_term, category)
        return jsonify({
            'success': True,
            'search_term': search_term,
            'category': category,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error searching data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get list of all categories"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        categories = storage.get_categories()
        return jsonify({
            'success': True,
            'categories': categories,
            'count': len(categories)
        })
        
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
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

@app.route('/api/optimize', methods=['POST'])
def optimize_storage():
    """Optimize storage"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        storage.optimize_storage()
        return jsonify({
            'success': True,
            'message': 'Storage optimized successfully'
        })
        
    except Exception as e:
        logger.error(f"Error optimizing storage: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup', methods=['POST'])
def backup_storage():
    """Backup storage"""
    if not check_api_key():
        return jsonify({'error': 'Invalid API key'}), 401
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{STORAGE_PATH}/backup_custom_data_{timestamp}.db"
        
        success = storage.backup_storage(backup_path)
        if success:
            return jsonify({
                'success': True,
                'message': 'Backup created successfully',
                'backup_path': backup_path
            })
        else:
            return jsonify({'error': 'Backup failed'}), 500
            
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return jsonify({'error': str(e)}), 500

# WebSocket events
if socketio:
    @socketio.on('connect')
    def handle_connect():
        """Handle WebSocket connection"""
        logger.info(f"Client connected: {request.sid}")
        emit('connected', {
            'message': 'Connected to Custom Data Storage',
            'storage_type': 'sqlite'
        })
    
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
    logger.info("Starting SQLite Custom Data Storage Add-on")
    logger.info(f"Storage path: {STORAGE_PATH}")
    logger.info(f"Storage type: SQLite Database")
    logger.info(f"Max storage size: {MAX_STORAGE_SIZE_MB}MB")
    logger.info(f"WebSocket enabled: {ENABLE_WEBSOCKET}")
    logger.info(f"CORS enabled: {ENABLE_CORS}")
    
    if socketio:
        socketio.run(app, host='0.0.0.0', port=8100, debug=(LOG_LEVEL == 'DEBUG'))
    else:
        app.run(host='0.0.0.0', port=8100, debug=(LOG_LEVEL == 'DEBUG'))
