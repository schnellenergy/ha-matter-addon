# 🗄️ Custom Data Storage Add-on

A Home Assistant add-on that provides **SQLite database storage** with REST API and WebSocket interface for storing and accessing custom data for your home automation applications.

## 🎯 Features

- **SQLite Database** - Professional SQL database with ACID compliance
- **REST API** - Full CRUD operations for data management
- **WebSocket** - Real-time data synchronization across devices
- **Categorized Storage** - Organize data by categories and keys
- **Persistent Storage** - Data survives restarts
- **Search Capability** - SQL-based search across all data
- **API Key Protection** - Optional authentication
- **CORS Support** - For web applications
- **Real-time Notifications** - WebSocket events for multi-device sync

---

# 📚 Complete Usage Documentation

## 🗄️ Database Architecture

### **Database Type: SQLite (SQL Database)**
- **Type**: Relational SQL Database
- **Engine**: SQLite 3.x
- **ACID Compliance**: Yes (Atomicity, Consistency, Isolation, Durability)
- **Concurrency**: Multiple readers, single writer with WAL mode
- **File Format**: Single binary database file

### **Storage Location:**
```
/data/custom_storage/custom_data.db    # Main database file
/data/custom_storage/custom_data.db-wal # Write-Ahead Log
/data/custom_storage/custom_data.db-shm # Shared memory file
```

---

## 🏗️ Database Schema

### **Main Data Table: `custom_data`**
```sql
CREATE TABLE custom_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,           -- JSON-encoded value
    value_type TEXT NOT NULL,      -- Python type name
    created_at TEXT NOT NULL,      -- ISO timestamp
    updated_at TEXT NOT NULL,      -- ISO timestamp
    UNIQUE(category, key)
);

-- Performance Indexes
CREATE INDEX idx_category_key ON custom_data(category, key);
CREATE INDEX idx_category ON custom_data(category);
CREATE INDEX idx_updated_at ON custom_data(updated_at);
```

---

# 🚀 Recommended 3-JSON Architecture for Home Automation

This architecture is optimized for **multi-user sync** and **large-scale home automation** systems.

## 📦 The 3 JSON Objects

### **Category: `home_automation`**

Store all data in one category with 3 keys:

1. **Key: `home_setup`** - Physical structure (floors, rooms, boxes)
2. **Key: `device_setup`** - Device details (SNAPs, docks, Matter nodes)
3. **Key: `configurations`** - UI settings and preferences

---

## 🏠 JSON 1: `home_setup` (Physical Structure)

```json
{
  "_version": 1,
  "_last_updated_by": "user_device_id_abc",
  "home_id": "home_1001",
  "name": "My Smart Home",
  "timezone": "Asia/Kolkata",
  "floors": [
    {
      "floor_id": "floor_2001",
      "name": "Ground Floor",
      "level": 0,
      "rooms": [
        {
          "room_id": "room_3001",
          "name": "Living Room",
          "icon": "living_room",
          "boxes": [
            {
              "box_id": "box_4001",
              "name": "Main Switchboard",
              "location_notes": "Behind the TV",
              "snap_ids": ["snap_5001", "snap_5002"]
            }
          ]
        },
        {
          "room_id": "room_3002",
          "name": "Kitchen",
          "icon": "kitchen",
          "boxes": [
            {
              "box_id": "box_4002",
              "name": "Appliance Board",
              "snap_ids": ["snap_5003"]
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 🔌 JSON 2: `device_setup` (Device Details)

**Flat lookup map** for O(1) device access:

```json
{
  "_version": 1,
  "_last_updated_by": "user_device_id_abc",
  "snaps": {
    "snap_5001": {
      "label": "Living Room Fan",
      "matter_node_id": "matter_node_aaa111",
      "type": "dimmer",
      "room_id": "room_3001",
      "box_id": "box_4001",
      "custom_icon": "🌀",
      "is_favorite": true
    },
    "snap_5002": {
      "label": "Living Light 1",
      "matter_node_id": "matter_node_bbb222",
      "type": "switch",
      "room_id": "room_3001",
      "box_id": "box_4001",
      "custom_icon": "💡",
      "is_favorite": false
    },
    "snap_5003": {
      "label": "Kitchen Chimney",
      "matter_node_id": "matter_node_ccc333",
      "type": "switch_heavy_duty",
      "room_id": "room_3002",
      "box_id": "box_4002"
    }
  },
  "docks": {
    "dock_9001": {
      "label": "Living Remote",
      "matter_node_id": "matter_node_eee555",
      "room_id": "room_3001",
      "battery_level": 88
    }
  }
}
```

---

## 🎛️ JSON 3: `configurations` (UI Settings)

```json
{
  "_version": 1,
  "_last_updated_by": "user_device_id_abc",
  "shared_preferences": {
    "ui_theme": "dark",
    "layout_mode": "grid"
  },
  "dashboard": {
    "pinned_devices": ["snap_5002", "snap_5001"],
    "quick_actions": ["scene_good_morning", "scene_movie_time"]
  },
  "scenes": {
    "scene_good_morning": {
      "name": "Good Morning",
      "actions": [
        { "device_id": "snap_5004", "state": "on" },
        { "device_id": "snap_5002", "state": "on" }
      ]
    }
  }
}
```

---

# 🔌 REST API Reference

**Base URL:** `http://homeassistant.local:8100`

## 1️⃣ Store Data (CREATE/UPDATE)

```bash
POST /api/data
Content-Type: application/json

{
  "category": "home_automation",
  "key": "home_setup",
  "value": { ...your_json_object... }
}
```

**Response:**
```json
{
  "success": true,
  "category": "home_automation",
  "key": "home_setup",
  "value": { ...your_json_object... },
  "timestamp": "2025-01-22T10:30:15.123Z"
}
```

---

## 2️⃣ Retrieve Specific Data (READ)

```bash
# Get specific key
GET /api/data/home_automation/home_setup

# Response
{
  "success": true,
  "category": "home_automation",
  "key": "home_setup",
  "value": { ...home_setup_json... }
}
```

---

## 3️⃣ Retrieve All Data in Category

```bash
# Get all keys in category
GET /api/data/home_automation

# Response
{
  "success": true,
  "category": "home_automation",
  "data": {
    "home_setup": { ...home_setup_json... },
    "device_setup": { ...device_setup_json... },
    "configurations": { ...configurations_json... }
  }
}
```

---

## 4️⃣ Search Data

```bash
GET /api/search?q=fan&category=home_automation

# Response
{
  "success": true,
  "search_term": "fan",
  "results": [
    {
      "category": "home_automation",
      "key": "device_setup",
      "value": { ...matching_data... },
      "updated_at": "2025-01-22T10:01:00Z"
    }
  ],
  "count": 1
}
```

---

## 5️⃣ Delete Data

```bash
DELETE /api/data/home_automation/home_setup

# Response
{
  "success": true,
  "message": "Deleted home_automation.home_setup"
}
```

---

## 6️⃣ Get Metadata

```bash
GET /api/metadata

# Response
{
  "total_values": 45,
  "total_categories": 5,
  "database_size_mb": 0.25,
  "storage_type": "sqlite",
  "categories": ["home_automation", "user_preferences"],
  "category_stats": {
    "home_automation": {
      "count": 3,
      "last_updated": "2025-01-22T10:30:15Z"
    }
  }
}
```

---

# 🔄 Multi-User Update Workflow

**Important:** This API uses **"Replace-Only"** updates. You cannot PATCH a single field.

### **The Read-Modify-Write Pattern:**

1. **GET** the current JSON from the hub
2. **MODIFY** the JSON locally in your app
3. **POST** the entire modified JSON back to the hub
4. **WebSocket** broadcasts the update to all connected devices

### **Example: Update a SNAP Label**

```dart
// 1. GET current data
final response = await dio.get('http://hub-ip:8100/api/data/home_automation/device_setup');
Map<String, dynamic> deviceSetup = response.data['value'];

// 2. MODIFY locally
deviceSetup['snaps']['snap_5001']['label'] = 'Ceiling Fan';
deviceSetup['_version'] = (deviceSetup['_version'] ?? 0) + 1;
deviceSetup['_last_updated_by'] = 'user_A_phone';

// 3. POST entire object back
await dio.post('http://hub-ip:8100/api/data', data: {
  'category': 'home_automation',
  'key': 'device_setup',
  'value': deviceSetup
});

// 4. WebSocket will notify all other devices automatically
```

---

# 📡 WebSocket API

## Connection

```javascript
const socket = io('http://homeassistant.local:8100');

socket.on('connect', () => {
  console.log('Connected to Custom Data Storage');
});

socket.on('connected', (data) => {
  console.log('Storage type:', data.storage_type);
});
```

---

## Real-time Data Updates

```javascript
socket.on('data_updated', (data) => {
  console.log('Data updated:', data);
  // data.action: 'set' or 'delete'
  // data.category: 'home_automation'
  // data.key: 'device_setup'
  // data.value: { ...new_json... }
  // data.timestamp: '2025-01-22T10:30:15Z'
  
  // Update your app's local state with data.value
});
```

---

## Request Data via WebSocket

```javascript
// Request specific data
socket.emit('get_data', {
  category: 'home_automation',
  key: 'device_setup'
});

// Listen for response
socket.on('data_response', (data) => {
  console.log('Data:', data.value);
});
```

---

# 📱 Flutter Integration Example

```dart
import 'package:dio/dio.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;

class HomeAutomationService {
  final Dio _dio = Dio();
  final String _baseUrl = 'http://192.168.1.100:8100';
  final String _category = 'home_automation';
  IO.Socket? _socket;

  // 1. INITIAL LOAD - Fetch all 3 JSONs at once
  Future<Map<String, dynamic>> fetchAllData() async {
    final response = await _dio.get('$_baseUrl/api/data/$_category');
    return response.data['data'] as Map<String, dynamic>;
  }

  // 2. UPDATE - Store modified JSON
  Future<void> storeData(String key, Map<String, dynamic> value) async {
    await _dio.post('$_baseUrl/api/data', data: {
      'category': _category,
      'key': key,
      'value': value,
    });
  }

  // 3. WEBSOCKET - Real-time sync
  void connectWebSocket(Function(Map<String, dynamic>) onUpdate) {
    _socket = IO.io(_baseUrl, <String, dynamic>{
      'transports': ['websocket'],
      'autoConnect': true,
    });

    _socket!.on('data_updated', (data) {
      if (data['category'] == _category) {
        onUpdate(data);
      }
    });
  }

  // 4. EXAMPLE: Update SNAP label
  Future<void> updateSnapLabel(
    Map<String, dynamic> currentDeviceSetup,
    String snapId,
    String newLabel
  ) async {
    // Deep copy
    final updated = Map<String, dynamic>.from(currentDeviceSetup);
    updated['snaps'] = Map<String, dynamic>.from(updated['snaps']);
    updated['snaps'][snapId] = Map<String, dynamic>.from(updated['snaps'][snapId]);
    
    // Modify
    updated['snaps'][snapId]['label'] = newLabel;
    updated['_version'] = (updated['_version'] ?? 0) + 1;
    
    // Store
    await storeData('device_setup', updated);
  }
}
```

---

# 💾 Direct Database Access

## Via Terminal & SSH Add-on

```bash
# Connect to database
sqlite3 /data/custom_storage/custom_data.db

# View all tables
.tables

# View data
.mode column
.headers on
SELECT category, key, value, updated_at FROM custom_data LIMIT 10;

# Search for devices
SELECT * FROM custom_data WHERE value LIKE '%fan%';

# Get statistics
SELECT category, COUNT(*) as count FROM custom_data GROUP BY category;

# Exit
.quit
```

---

# 🏠 Home Assistant Integration

## Create Sensors

```yaml
# configuration.yaml
sensor:
  - platform: rest
    name: "Custom Data Count"
    resource: "http://localhost:8100/api/metadata"
    value_template: "{{ value_json.total_values }}"
    json_attributes:
      - total_categories
      - database_size_mb

  - platform: rest
    name: "Home Setup"
    resource: "http://localhost:8100/api/data/home_automation/home_setup"
    value_template: "{{ value_json.value.name }}"
    json_attributes_path: "$.value"
    json_attributes:
      - home_id
      - floors
```

---

## REST Commands

```yaml
# configuration.yaml
rest_command:
  update_device_label:
    url: "http://localhost:8100/api/data"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: >
      {
        "category": "home_automation",
        "key": "device_setup",
        "value": {{ device_setup | tojson }}
      }
```

---

# 🔧 Database Operations

## Optimize Database

```bash
curl -X POST http://homeassistant.local:8100/api/optimize
```

## Backup Database

```bash
# Via API
curl -X POST http://homeassistant.local:8100/api/backup

# Manual backup
cp /data/custom_storage/custom_data.db /backup/custom_data_backup.db

# Restore
cp /backup/custom_data_backup.db /data/custom_storage/custom_data.db
```

---

# 📊 Performance Characteristics

### **Capacity:**
- **Maximum database size**: 281 TB (theoretical)
- **Maximum row count**: 2^64 rows
- **Practical limit**: 100MB (configurable)

### **Performance:**
- **Read operations**: < 1ms (with indexes)
- **Write operations**: < 1ms (WAL mode)
- **Search operations**: < 10ms
- **Concurrent readers**: Unlimited
- **Concurrent writers**: 1 (with queuing)

---

# ⚙️ Configuration

```yaml
log_level: info                          # Log level
storage_path: /data/custom_storage       # Storage directory
max_storage_size_mb: 100                 # Max size in MB
enable_websocket: true                   # Enable WebSocket
enable_cors: true                        # Enable CORS
api_key: ""                              # Optional API key
```

---

# 🎯 Summary

**This Custom Data Storage add-on provides:**

✅ **Enterprise-grade SQLite database** with ACID compliance  
✅ **REST API** for all CRUD operations  
✅ **WebSocket API** for real-time multi-device sync  
✅ **Direct SQL access** for advanced queries  
✅ **Home Assistant integration** via sensors and REST commands  
✅ **Professional features** (backup, optimization, search)  
✅ **Optimized 3-JSON architecture** for home automation  
✅ **Multi-user safe** with Read-Modify-Write pattern  

**Perfect for large-scale home automation systems with multiple users and devices!** 🚀📊

---

# 📚 Additional Documentation

For more detailed guides, see the [documents](documents/) folder:

- **[Quick Start Guide](documents/QUICK_START.md)** - 3-step installation
- **[Complete SQLite Documentation](documents/COMPLETE_SQLITE_DOCUMENTATION.md)** - Full technical details
- **[Usage Documentation](documents/usage_documentation)** - Advanced examples
- **[Troubleshooting](documents/TROUBLESHOOTING.md)** - Common issues

---

# 🚀 Quick Installation

1. Copy `custom_data_storage` folder to `\\homeassistant.local\addon\local\` via Samba
2. SSH into Home Assistant and run:
   ```bash
   cd /addon/local/custom_data_storage
   chmod +x diagnose_addon.sh
   ./diagnose_addon.sh
   ```
3. In Home Assistant UI: **Settings → Add-ons → ⋮ → Reload**
4. Install from "Local add-ons" section
5. Configure and Start the add-on

**The add-on will be available at:** `http://homeassistant.local:8100`

---

**Made with ❤️ for Schnell Home Automation**
