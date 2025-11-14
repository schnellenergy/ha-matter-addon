#!/usr/bin/env python3
"""
Basic functionality test for SQLite Custom Data Storage Add-on
Tests core functionality to identify any errors
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_database_storage():
    """Test DatabaseStorage class directly"""
    print("🧪 Testing DatabaseStorage class...")
    
    try:
        from database_storage import DatabaseStorage
        print("✅ DatabaseStorage import successful")
    except Exception as e:
        print(f"❌ DatabaseStorage import failed: {e}")
        return False
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp()
    try:
        # Initialize storage
        storage = DatabaseStorage(temp_dir)
        print("✅ DatabaseStorage initialization successful")
        
        # Test storing data
        result = storage.set_value('test_key', 'test_value', 'test_category')
        if result.get('success'):
            print("✅ Data storage successful")
        else:
            print(f"❌ Data storage failed: {result}")
            return False
        
        # Test retrieving data
        value = storage.get_value('test_key', 'test_category')
        if value == 'test_value':
            print("✅ Data retrieval successful")
        else:
            print(f"❌ Data retrieval failed: expected 'test_value', got {value}")
            return False
        
        # Test metadata
        metadata = storage.get_metadata()
        if metadata and 'total_values' in metadata:
            print(f"✅ Metadata retrieval successful: {metadata['total_values']} values")
        else:
            print(f"❌ Metadata retrieval failed: {metadata}")
            return False
        
        print("✅ DatabaseStorage tests passed")
        return True
        
    except Exception as e:
        print(f"❌ DatabaseStorage test error: {e}")
        return False
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_main_app_imports():
    """Test main application imports"""
    print("\n🧪 Testing main application imports...")
    
    try:
        # Set environment variables for testing
        os.environ['LOG_LEVEL'] = 'INFO'
        os.environ['STORAGE_PATH'] = tempfile.mkdtemp()
        os.environ['MAX_STORAGE_SIZE_MB'] = '100'
        os.environ['ENABLE_WEBSOCKET'] = 'false'
        os.environ['ENABLE_CORS'] = 'true'
        os.environ['API_KEY'] = ''
        
        # Import main application
        from main_enhanced import app, storage, StorageManager
        print("✅ Main application imports successful")
        
        # Test StorageManager
        temp_dir = tempfile.mkdtemp()
        test_storage = StorageManager(temp_dir)
        print("✅ StorageManager initialization successful")
        
        # Test basic operations
        result = test_storage.set_value('test', 'value', 'category')
        if result.get('success'):
            print("✅ StorageManager set_value successful")
        else:
            print(f"❌ StorageManager set_value failed: {result}")
            return False
        
        value = test_storage.get_value('test', 'category')
        if value == 'value':
            print("✅ StorageManager get_value successful")
        else:
            print(f"❌ StorageManager get_value failed: {value}")
            return False
        
        print("✅ Main application tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Main application test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_flask_app():
    """Test Flask application setup"""
    print("\n🧪 Testing Flask application setup...")
    
    try:
        from main_enhanced import app
        
        # Test app configuration
        if app.config.get('SECRET_KEY'):
            print("✅ Flask app configuration successful")
        else:
            print("❌ Flask app configuration missing")
            return False
        
        # Test app context
        with app.app_context():
            print("✅ Flask app context successful")
        
        print("✅ Flask application tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Flask application test error: {e}")
        return False

def test_dependencies():
    """Test required dependencies"""
    print("\n🧪 Testing dependencies...")
    
    dependencies = [
        'flask',
        'flask_cors',
        'flask_socketio',
        'eventlet',
        'sqlite3',
        'json',
        'logging',
        'pathlib',
        'datetime'
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✅ {dep} import successful")
        except ImportError as e:
            print(f"❌ {dep} import failed: {e}")
            return False
    
    print("✅ All dependencies available")
    return True

def main():
    """Run all tests"""
    print("🚀 Starting SQLite Custom Data Storage Add-on Tests")
    print("=" * 60)
    
    tests = [
        ("Dependencies", test_dependencies),
        ("DatabaseStorage", test_database_storage),
        ("Main Application", test_main_app_imports),
        ("Flask Application", test_flask_app),
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
    
    print("\n" + "="*60)
    print(f"🧪 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Add-on is ready to use.")
        return True
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
