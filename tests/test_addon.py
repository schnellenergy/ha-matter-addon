#!/usr/bin/env python3
"""
Test script for Custom Data Storage Add-on
Tests all API endpoints and WebSocket functionality
"""

import requests
import json
import time
import socketio
from datetime import datetime

class CustomDataStorageTest:
    def __init__(self, base_url="http://localhost:8100", api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers['X-API-Key'] = api_key
        
        self.sio = socketio.Client()
        self.websocket_events = []
        
    def setup_websocket(self):
        """Setup WebSocket event handlers"""
        @self.sio.event
        def connect():
            print("✅ WebSocket connected")
            
        @self.sio.event
        def disconnect():
            print("❌ WebSocket disconnected")
            
        @self.sio.event
        def data_updated(data):
            print(f"📊 WebSocket data update: {data}")
            self.websocket_events.append(data)
            
        @self.sio.event
        def data_response(data):
            print(f"📊 WebSocket data response: {data}")
            
    def test_health_check(self):
        """Test health check endpoint"""
        print("\n🏥 Testing health check...")
        try:
            response = requests.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Health check passed: {data['status']}")
                print(f"   Storage size: {data['storage_size_mb']} MB")
                print(f"   WebSocket enabled: {data['websocket_enabled']}")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def test_store_data(self):
        """Test storing data"""
        print("\n💾 Testing data storage...")
        test_data = [
            {"key": "theme", "value": "dark", "category": "user_preferences"},
            {"key": "language", "value": "en", "category": "user_preferences"},
            {"key": "auto_refresh", "value": 30, "category": "app_config"},
            {"key": "fan.living_room", "value": {"name": "Main Fan", "icon": "🌀"}, "category": "devices"},
            {"key": "test_boolean", "value": True, "category": "test"},
            {"key": "test_number", "value": 42.5, "category": "test"},
            {"key": "test_list", "value": [1, 2, 3, "test"], "category": "test"},
        ]
        
        success_count = 0
        for data in test_data:
            try:
                response = requests.post(
                    f"{self.base_url}/api/data",
                    json=data,
                    headers=self.headers
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        print(f"✅ Stored: {data['category']}.{data['key']} = {data['value']}")
                        success_count += 1
                    else:
                        print(f"❌ Failed to store: {data}")
                else:
                    print(f"❌ HTTP error storing {data}: {response.status_code}")
            except Exception as e:
                print(f"❌ Error storing {data}: {e}")
        
        print(f"📊 Storage test: {success_count}/{len(test_data)} successful")
        return success_count == len(test_data)
    
    def test_get_data(self):
        """Test retrieving data"""
        print("\n📖 Testing data retrieval...")
        test_cases = [
            ("user_preferences", "theme"),
            ("user_preferences", "language"),
            ("app_config", "auto_refresh"),
            ("devices", "fan.living_room"),
            ("test", "test_boolean"),
            ("test", "test_number"),
            ("test", "test_list"),
        ]
        
        success_count = 0
        for category, key in test_cases:
            try:
                response = requests.get(
                    f"{self.base_url}/api/data/{category}/{key}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        print(f"✅ Retrieved: {category}.{key} = {result['value']}")
                        success_count += 1
                    else:
                        print(f"❌ Failed to retrieve: {category}.{key}")
                else:
                    print(f"❌ HTTP error retrieving {category}.{key}: {response.status_code}")
            except Exception as e:
                print(f"❌ Error retrieving {category}.{key}: {e}")
        
        print(f"📊 Retrieval test: {success_count}/{len(test_cases)} successful")
        return success_count == len(test_cases)
    
    def test_get_category_data(self):
        """Test retrieving category data"""
        print("\n📂 Testing category data retrieval...")
        categories = ["user_preferences", "app_config", "devices", "test"]
        
        success_count = 0
        for category in categories:
            try:
                response = requests.get(
                    f"{self.base_url}/api/data/{category}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        data = result['data']
                        print(f"✅ Category {category}: {len(data)} items")
                        success_count += 1
                    else:
                        print(f"❌ Failed to retrieve category: {category}")
                else:
                    print(f"❌ HTTP error retrieving category {category}: {response.status_code}")
            except Exception as e:
                print(f"❌ Error retrieving category {category}: {e}")
        
        print(f"📊 Category retrieval test: {success_count}/{len(categories)} successful")
        return success_count == len(categories)
    
    def test_get_all_data(self):
        """Test retrieving all data"""
        print("\n🗂️ Testing all data retrieval...")
        try:
            response = requests.get(
                f"{self.base_url}/api/data",
                headers=self.headers
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    data = result['data']
                    total_categories = len(data)
                    total_items = sum(len(category_data) for category_data in data.values())
                    print(f"✅ Retrieved all data: {total_categories} categories, {total_items} total items")
                    return True
                else:
                    print("❌ Failed to retrieve all data")
                    return False
            else:
                print(f"❌ HTTP error retrieving all data: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error retrieving all data: {e}")
            return False
    
    def test_metadata(self):
        """Test metadata retrieval"""
        print("\n📊 Testing metadata retrieval...")
        try:
            response = requests.get(
                f"{self.base_url}/api/metadata",
                headers=self.headers
            )
            if response.status_code == 200:
                metadata = response.json()
                print(f"✅ Metadata retrieved:")
                print(f"   Total keys: {metadata.get('total_keys', 0)}")
                print(f"   Total updates: {metadata.get('total_updates', 0)}")
                print(f"   Storage size: {metadata.get('storage_size_mb', 0)} MB")
                print(f"   Categories: {metadata.get('categories', [])}")
                print(f"   Total values: {metadata.get('total_values', 0)}")
                return True
            else:
                print(f"❌ HTTP error retrieving metadata: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error retrieving metadata: {e}")
            return False
    
    def test_delete_data(self):
        """Test deleting data"""
        print("\n🗑️ Testing data deletion...")
        test_cases = [
            ("test", "test_boolean"),
            ("test", "test_number"),
            ("test", "test_list"),
        ]
        
        success_count = 0
        for category, key in test_cases:
            try:
                response = requests.delete(
                    f"{self.base_url}/api/data/{category}/{key}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        print(f"✅ Deleted: {category}.{key}")
                        success_count += 1
                    else:
                        print(f"❌ Failed to delete: {category}.{key}")
                else:
                    print(f"❌ HTTP error deleting {category}.{key}: {response.status_code}")
            except Exception as e:
                print(f"❌ Error deleting {category}.{key}: {e}")
        
        print(f"📊 Deletion test: {success_count}/{len(test_cases)} successful")
        return success_count == len(test_cases)
    
    def test_websocket(self):
        """Test WebSocket functionality"""
        print("\n🔌 Testing WebSocket...")
        try:
            self.setup_websocket()
            self.sio.connect(self.base_url)
            
            # Wait for connection
            time.sleep(1)
            
            if self.sio.connected:
                print("✅ WebSocket connected successfully")
                
                # Test data request via WebSocket
                self.sio.emit('get_data', {'category': 'user_preferences', 'key': 'theme'})
                time.sleep(1)
                
                # Store new data to trigger WebSocket event
                requests.post(
                    f"{self.base_url}/api/data",
                    json={"key": "websocket_test", "value": "test_value", "category": "test"},
                    headers=self.headers
                )
                
                # Wait for WebSocket event
                time.sleep(2)
                
                self.sio.disconnect()
                
                if self.websocket_events:
                    print(f"✅ WebSocket events received: {len(self.websocket_events)}")
                    return True
                else:
                    print("⚠️ No WebSocket events received")
                    return False
            else:
                print("❌ WebSocket connection failed")
                return False
                
        except Exception as e:
            print(f"❌ WebSocket test error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("🧪 Starting Custom Data Storage Add-on Tests")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"🔑 API Key: {'Set' if self.api_key else 'Not set'}")
        print("=" * 50)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Store Data", self.test_store_data),
            ("Get Data", self.test_get_data),
            ("Get Category Data", self.test_get_category_data),
            ("Get All Data", self.test_get_all_data),
            ("Metadata", self.test_metadata),
            ("Delete Data", self.test_delete_data),
            ("WebSocket", self.test_websocket),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} {'='*20}")
            try:
                if test_func():
                    passed += 1
                    print(f"✅ {test_name} PASSED")
                else:
                    print(f"❌ {test_name} FAILED")
            except Exception as e:
                print(f"❌ {test_name} ERROR: {e}")
        
        print("\n" + "="*50)
        print(f"🧪 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! Custom Data Storage Add-on is working correctly.")
        else:
            print("⚠️ Some tests failed. Check the add-on configuration and logs.")
        
        return passed == total

if __name__ == "__main__":
    import sys
    
    # Default configuration
    base_url = "http://localhost:8100"
    api_key = None
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    if len(sys.argv) > 2:
        api_key = sys.argv[2]
    
    # Run tests
    tester = CustomDataStorageTest(base_url, api_key)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)
