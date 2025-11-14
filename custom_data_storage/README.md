# 🗄️ Custom Data Storage Add-on

A Home Assistant add-on that provides REST API and WebSocket interface for storing and accessing custom values for your home automation app.

## 🎯 Features

- **REST API** for storing and retrieving custom data
- **WebSocket** for real-time data updates
- **Categorized Storage** organize data by categories
- **Persistent Storage** data survives restarts
- **Size Limits** configurable storage size limits
- **API Key Protection** optional API key authentication
- **CORS Support** for web applications
- **Real-time Notifications** WebSocket events for data changes

## 📚 Documentation

**For installation instructions, troubleshooting, and detailed guides, see the [documents](documents/) folder:**

- **[Quick Start Guide](documents/QUICK_START.md)** - 3-step installation
- **[Installation Guide](documents/FIXED_INSTALLATION_STEPS.md)** - Detailed setup with troubleshooting
- **[Troubleshooting](documents/TROUBLESHOOTING.md)** - Common issues and solutions
- **[All Documentation](documents/README.md)** - Complete documentation index

## 🚀 Quick Installation

1. Copy `custom_data_storage` folder to `\\homeassistant.local\addon\local\` via Samba
2. SSH into Home Assistant and run:
   ```bash
   cd /addon/local/custom_data_storage
   chmod +x diagnose_addon.sh
   ./diagnose_addon.sh
   ```
3. In Home Assistant UI: **Settings → Add-ons → ⋮ → Reload**
4. Install from "Local add-ons" section

**See [documents/QUICK_START.md](documents/QUICK_START.md) for detailed steps.**

## ⚙️ Configuration

```yaml
log_level: info              # Log level (trace, debug, info, warning, error, fatal)
storage_path: /data/custom_storage  # Storage directory path
max_storage_size_mb: 100     # Maximum storage size in MB
enable_websocket: true       # Enable WebSocket support
enable_cors: true           # Enable CORS for web apps
api_key: ""                 # Optional API key for authentication
```

## 🌐 API Endpoints

### Base URL
```
http://your-ha-ip:8100
```

### Health Check
```http
GET /health
```

### Store Data
```http
POST /api/data
Content-Type: application/json
X-API-Key: your-api-key (if configured)

{
  "key": "user_preference",
  "value": "dark_mode",
  "category": "ui_settings"
}
```

### Get Specific Data
```http
GET /api/data/{category}/{key}
X-API-Key: your-api-key (if configured)
```

### Get All Data in Category
```http
GET /api/data/{category}
X-API-Key: your-api-key (if configured)
```

### Get All Data
```http
GET /api/data
X-API-Key: your-api-key (if configured)
```

### Delete Data
```http
DELETE /api/data/{category}/{key}
X-API-Key: your-api-key (if configured)
```

### Get Metadata
```http
GET /api/metadata
X-API-Key: your-api-key (if configured)
```

## 🔌 WebSocket Events

### Connect to WebSocket
```javascript
const socket = io('http://your-ha-ip:8100');
```

### Listen for Data Updates
```javascript
socket.on('data_updated', (data) => {
  console.log('Data updated:', data);
  // data.action: 'set' or 'delete'
  // data.category: category name
  // data.key: data key
  // data.value: new value (for 'set' action)
  // data.timestamp: update timestamp
});
```

### Request Data via WebSocket
```javascript
socket.emit('get_data', {
  category: 'ui_settings',
  key: 'user_preference'
});

socket.on('data_response', (data) => {
  console.log('Data response:', data);
});
```

## 📱 Flutter Integration Example

```dart
import 'package:dio/dio.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;

class CustomDataService {
  final Dio _dio = Dio();
  final String baseUrl = 'http://192.168.1.100:8100';
  final String? apiKey = 'your-api-key';
  IO.Socket? _socket;

  // Store data
  Future<void> storeData(String key, dynamic value, {String category = 'default'}) async {
    try {
      final response = await _dio.post(
        '$baseUrl/api/data',
        data: {
          'key': key,
          'value': value,
          'category': category,
        },
        options: Options(
          headers: apiKey != null ? {'X-API-Key': apiKey} : null,
        ),
      );
      print('Data stored: ${response.data}');
    } catch (e) {
      print('Error storing data: $e');
    }
  }

  // Get data
  Future<dynamic> getData(String key, {String category = 'default'}) async {
    try {
      final response = await _dio.get(
        '$baseUrl/api/data/$category/$key',
        options: Options(
          headers: apiKey != null ? {'X-API-Key': apiKey} : null,
        ),
      );
      return response.data['value'];
    } catch (e) {
      print('Error getting data: $e');
      return null;
    }
  }

  // Connect to WebSocket
  void connectWebSocket() {
    _socket = IO.io(baseUrl, <String, dynamic>{
      'transports': ['websocket'],
    });

    _socket!.on('connect', (_) {
      print('Connected to Custom Data Storage WebSocket');
    });

    _socket!.on('data_updated', (data) {
      print('Data updated: $data');
      // Handle real-time data updates
    });
  }

  // Disconnect WebSocket
  void disconnectWebSocket() {
    _socket?.disconnect();
  }
}
```

## 📊 Data Structure

### Stored Data Format
```json
{
  "category_name": {
    "key_name": {
      "value": "actual_value",
      "timestamp": "2025-01-22T10:30:15.123Z",
      "type": "str"
    }
  }
}
```

### Metadata Format
```json
{
  "created_at": "2025-01-22T10:00:00.000Z",
  "last_updated": "2025-01-22T10:30:15.123Z",
  "total_keys": 5,
  "total_updates": 12,
  "storage_size_mb": 0.05,
  "max_storage_size_mb": 100,
  "categories": ["default", "ui_settings", "user_data"],
  "total_values": 5
}
```

## 🔐 Security

### API Key Authentication
If you set an `api_key` in the configuration, all API requests must include it:

**Header Method:**
```http
X-API-Key: your-secret-api-key
```

**Query Parameter Method:**
```http
GET /api/data?api_key=your-secret-api-key
```

### CORS Configuration
CORS is enabled by default for web applications. You can disable it by setting `enable_cors: false`.

## 📝 Use Cases

### 1. User Preferences
```bash
# Store user theme preference
curl -X POST http://192.168.1.100:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "theme", "value": "dark", "category": "user_preferences"}'

# Get user theme preference
curl http://192.168.1.100:8100/api/data/user_preferences/theme
```

### 2. App Configuration
```bash
# Store app settings
curl -X POST http://192.168.1.100:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "auto_refresh_interval", "value": 30, "category": "app_config"}'
```

### 3. Device Custom Properties
```bash
# Store custom device properties
curl -X POST http://192.168.1.100:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "fan.living_room", "value": {"custom_name": "Main Fan", "room_icon": "🌀"}, "category": "device_properties"}'
```

## 🔧 Troubleshooting

### Check Add-on Logs
1. Go to Settings → Add-ons → Custom Data Storage
2. Click on "Log" tab
3. Look for error messages

### Test API Connectivity
```bash
# Test health endpoint
curl http://your-ha-ip:8100/health

# Test data storage
curl -X POST http://your-ha-ip:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": "hello"}'
```

### Common Issues

1. **Port 8100 not accessible**: Check if the add-on is running and port is exposed
2. **API key errors**: Verify the API key is correctly set in configuration
3. **Storage full**: Check storage size and increase `max_storage_size_mb` if needed
4. **WebSocket connection fails**: Ensure `enable_websocket: true` in configuration

## 📚 API Response Examples

### Successful Data Storage
```json
{
  "success": true,
  "category": "user_preferences",
  "key": "theme",
  "value": "dark",
  "timestamp": "2025-01-22T10:30:15.123Z"
}
```

### Data Retrieval
```json
{
  "success": true,
  "category": "user_preferences",
  "key": "theme",
  "value": "dark"
}
```

### Error Response
```json
{
  "error": "Key not found"
}
```

## 🎯 Integration with Your Home Automation App

This add-on is perfect for storing:
- User preferences and settings
- Custom device properties
- App configuration values
- Temporary data that needs persistence
- Real-time shared data between app instances

The WebSocket support ensures your app gets real-time updates when data changes from other sources!

## 🔄 Port Information

- **Custom Data Storage**: Port 8100
- **HA Data Collector**: Port 8099 (your existing add-on)
- **Home Assistant**: Port 8123 (default)

This ensures no port conflicts between your add-ons.
