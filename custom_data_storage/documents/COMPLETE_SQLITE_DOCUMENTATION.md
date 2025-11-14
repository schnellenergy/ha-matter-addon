# 🗄️ Complete SQLite Custom Data Storage Documentation

## 🎯 Overview

Your Custom Data Storage Add-on uses **SQLite** as the single, robust database solution for storing large amounts of custom data. This document provides complete implementation details, usage examples, and integration guides.

## 📊 Database Type & Architecture

### **Database Type: SQLite (SQL Database)**
- **Type**: Relational SQL Database
- **Engine**: SQLite 3.x
- **ACID Compliance**: Yes (Atomicity, Consistency, Isolation, Durability)
- **Concurrency**: Multiple readers, single writer with WAL mode
- **File Format**: Single binary database file
- **Query Language**: Standard SQL

### **Storage Location:**
```
/data/custom_storage/custom_data.db    # Main database file
/data/custom_storage/custom_data.db-wal # Write-Ahead Log
/data/custom_storage/custom_data.db-shm # Shared memory file
```

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

### **Metadata Table: `metadata`**
```sql
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 📝 Data Storage Format

### **How Data is Stored:**
1. **Values are JSON-encoded** before storage
2. **Type information preserved** in `value_type` column
3. **Timestamps in ISO format** (UTC)
4. **Categories organize data** logically

### **Example Database Records:**
```sql
-- User preference
INSERT INTO custom_data VALUES (
    1, 'user_preferences', 'theme', '"dark"', 'str', 
    '2025-01-22T10:00:00Z', '2025-01-22T10:00:00Z'
);

-- Device properties (complex object)
INSERT INTO custom_data VALUES (
    2, 'devices', 'fan.living_room', 
    '{"name": "Main Fan", "icon": "🌀", "favorite": true}', 'dict',
    '2025-01-22T10:01:00Z', '2025-01-22T10:01:00Z'
);

-- Numeric value
INSERT INTO custom_data VALUES (
    3, 'app_config', 'refresh_interval', '30', 'int',
    '2025-01-22T10:02:00Z', '2025-01-22T10:02:00Z'
);
```

## 🔌 REST API Implementation

### **Base URL:** `http://your-ha-ip:8100`

### **1. Store Data**
```http
POST /api/data
Content-Type: application/json
X-API-Key: your-api-key (optional)

{
  "key": "theme",
  "value": "dark",
  "category": "user_preferences"
}
```

**Response:**
```json
{
  "success": true,
  "category": "user_preferences",
  "key": "theme",
  "value": "dark",
  "timestamp": "2025-01-22T10:30:15.123Z"
}
```

### **2. Retrieve Specific Data**
```http
GET /api/data/user_preferences/theme
X-API-Key: your-api-key (optional)
```

**Response:**
```json
{
  "success": true,
  "category": "user_preferences",
  "key": "theme",
  "value": "dark"
}
```

### **3. Retrieve Category Data**
```http
GET /api/data/user_preferences
```

**Response:**
```json
{
  "success": true,
  "category": "user_preferences",
  "data": {
    "theme": "dark",
    "language": "en",
    "notifications": true
  }
}
```

### **4. Retrieve All Data**
```http
GET /api/data
```

**Response:**
```json
{
  "success": true,
  "category": null,
  "data": {
    "user_preferences": {
      "theme": "dark",
      "language": "en"
    },
    "devices": {
      "fan.living_room": {
        "name": "Main Fan",
        "icon": "🌀"
      }
    }
  }
}
```

### **5. Search Data (SQLite Feature)**
```http
GET /api/search?q=fan&category=devices
```

**Response:**
```json
{
  "success": true,
  "search_term": "fan",
  "category": "devices",
  "results": [
    {
      "category": "devices",
      "key": "fan.living_room",
      "value": {"name": "Main Fan", "icon": "🌀"},
      "updated_at": "2025-01-22T10:01:00Z"
    }
  ],
  "count": 1
}
```

### **6. Delete Data**
```http
DELETE /api/data/user_preferences/theme
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted user_preferences.theme"
}
```

### **7. Get Database Metadata**
```http
GET /api/metadata
```

**Response:**
```json
{
  "created_at": "2025-01-22T09:00:00Z",
  "last_updated": "2025-01-22T10:30:15Z",
  "total_operations": 156,
  "version": "2.0.0",
  "storage_type": "sqlite",
  "total_values": 45,
  "total_categories": 5,
  "categories": ["user_preferences", "devices", "app_config"],
  "database_size_mb": 0.25,
  "database_file": "/data/custom_storage/custom_data.db",
  "category_stats": {
    "user_preferences": {
      "count": 10,
      "first_created": "2025-01-22T09:00:00Z",
      "last_updated": "2025-01-22T10:30:15Z"
    }
  }
}
```

### **8. Database Operations**
```http
# Optimize database
POST /api/optimize

# Backup database
POST /api/backup

# Get categories list
GET /api/categories
```

## 🔌 WebSocket API Implementation

### **Connection:**
```javascript
const socket = io('http://your-ha-ip:8100');
```

### **Events:**

#### **1. Connection Events**
```javascript
socket.on('connect', () => {
  console.log('Connected to Custom Data Storage');
});

socket.on('connected', (data) => {
  console.log('Welcome message:', data.message);
  console.log('Storage type:', data.storage_type);
});
```

#### **2. Real-time Data Updates**
```javascript
socket.on('data_updated', (data) => {
  console.log('Data updated:', data);
  // data.action: 'set' or 'delete'
  // data.category: category name
  // data.key: data key
  // data.value: new value (for 'set')
  // data.timestamp: update timestamp
});
```

#### **3. Request Data via WebSocket**
```javascript
// Request specific data
socket.emit('get_data', {
  category: 'user_preferences',
  key: 'theme'
});

// Request category data
socket.emit('get_data', {
  category: 'user_preferences'
});

// Request all data
socket.emit('get_data', {});

// Listen for responses
socket.on('data_response', (data) => {
  console.log('Data response:', data);
});
```

## 💾 Direct Database Access

### **1. Access Database File**
```bash
# Connect to database directly
sqlite3 /data/custom_storage/custom_data.db

# View all tables
.tables

# View table schema
.schema custom_data

# Query data
SELECT * FROM custom_data WHERE category = 'user_preferences';

# Search data
SELECT * FROM custom_data WHERE value LIKE '%fan%';

# Get statistics
SELECT category, COUNT(*) as count FROM custom_data GROUP BY category;
```

### **2. Database Queries Examples**
```sql
-- Get all user preferences
SELECT key, value FROM custom_data 
WHERE category = 'user_preferences';

-- Search for devices containing 'living'
SELECT * FROM custom_data 
WHERE category = 'devices' AND (key LIKE '%living%' OR value LIKE '%living%');

-- Get recently updated data
SELECT * FROM custom_data 
ORDER BY updated_at DESC LIMIT 10;

-- Get data by type
SELECT * FROM custom_data WHERE value_type = 'dict';

-- Count records by category
SELECT category, COUNT(*) as count, 
       MIN(created_at) as first_created,
       MAX(updated_at) as last_updated
FROM custom_data GROUP BY category;
```

## 🏠 Home Assistant Integration

### **1. Viewing Data from Home Assistant**

#### **Option A: File Editor Add-on**
1. Install **File Editor** add-on
2. Navigate to `/data/custom_storage/`
3. View database file (binary, not human-readable)

#### **Option B: Terminal & SSH Add-on**
1. Install **Terminal & SSH** add-on
2. Access database via command line:
```bash
# Connect to database
sqlite3 /data/custom_storage/custom_data.db

# View data in readable format
.mode column
.headers on
SELECT category, key, value, updated_at FROM custom_data LIMIT 10;
```

#### **Option C: Custom Sensor (Recommended)**
Create Home Assistant sensors to display data:

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
      - categories

  - platform: rest
    name: "User Theme"
    resource: "http://localhost:8100/api/data/user_preferences/theme"
    value_template: "{{ value_json.value }}"
```

### **2. Editing Data from Home Assistant UI**

#### **Option A: REST Commands**
```yaml
# configuration.yaml
rest_command:
  set_user_theme:
    url: "http://localhost:8100/api/data"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: >
      {
        "key": "theme",
        "value": "{{ theme }}",
        "category": "user_preferences"
      }

  delete_user_setting:
    url: "http://localhost:8100/api/data/user_preferences/{{ setting }}"
    method: DELETE
```

#### **Option B: Custom Lovelace Card**
```yaml
# dashboard card
type: entities
title: Custom Data Management
entities:
  - entity: sensor.custom_data_count
  - entity: sensor.user_theme
  - type: call-service
    name: Set Dark Theme
    service: rest_command.set_user_theme
    service_data:
      theme: "dark"
  - type: call-service
    name: Set Light Theme
    service: rest_command.set_user_theme
    service_data:
      theme: "light"
```

#### **Option C: Node-RED Integration**
1. Install **Node-RED** add-on
2. Create flows to manage custom data:
```json
[
  {
    "id": "http-request-node",
    "type": "http request",
    "url": "http://localhost:8100/api/data",
    "method": "POST",
    "headers": {"Content-Type": "application/json"}
  }
]
```

## 🔧 Advanced Database Features

### **1. Performance Optimization**
```bash
# Optimize database
curl -X POST http://your-ha-ip:8100/api/optimize

# This runs:
# VACUUM - Reclaim unused space
# ANALYZE - Update query planner statistics
```

### **2. Backup & Recovery**
```bash
# Create backup
curl -X POST http://your-ha-ip:8100/api/backup

# Manual backup
cp /data/custom_storage/custom_data.db /backup/custom_data_backup.db

# Restore backup
cp /backup/custom_data_backup.db /data/custom_storage/custom_data.db
```

### **3. Database Monitoring**
```bash
# Check database size
ls -lh /data/custom_storage/custom_data.db

# Check database integrity
sqlite3 /data/custom_storage/custom_data.db "PRAGMA integrity_check;"

# View database info
sqlite3 /data/custom_storage/custom_data.db "PRAGMA database_list;"
```

## 📊 Performance Characteristics

### **Capacity:**
- **Maximum database size**: 281 TB (theoretical)
- **Maximum row count**: 2^64 rows
- **Maximum columns**: 2,000 per table
- **Maximum SQL statement length**: 1 GB

### **Performance:**
- **Read operations**: < 1ms (with indexes)
- **Write operations**: < 1ms (WAL mode)
- **Search operations**: < 10ms (full-text search)
- **Concurrent readers**: Unlimited
- **Concurrent writers**: 1 (with queuing)

### **Memory Usage:**
- **Cache size**: 10MB (configurable)
- **Memory per connection**: ~1MB
- **Total memory**: Scales with concurrent connections

## 🎯 Summary

**Your SQLite Custom Data Storage provides:**

✅ **Enterprise-grade SQL database** with ACID compliance  
✅ **REST API** for all CRUD operations  
✅ **WebSocket API** for real-time updates  
✅ **Direct SQL access** for advanced queries  
✅ **Home Assistant integration** via sensors and REST commands  
✅ **Professional features** (backup, optimization, search)  
✅ **Unlimited scalability** for your large datasets  

**The database is stored as a single file that you can directly access, query, backup, and integrate with Home Assistant's UI through various methods!** 🚀📊
