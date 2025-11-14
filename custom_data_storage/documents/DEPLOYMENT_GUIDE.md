# 🚀 Custom Data Storage Add-on Deployment Guide

## 📋 Overview

This guide will help you deploy the Custom Data Storage add-on to your Home Assistant instance. The add-on provides REST API and WebSocket access for storing custom values for your home automation app.

## 🎯 Features Summary

- **REST API** on port 8100 for data storage/retrieval
- **WebSocket** for real-time data updates
- **Categorized Storage** organize data by categories
- **Persistent Storage** survives restarts
- **API Key Protection** optional authentication
- **Size Limits** configurable storage limits

## 📦 Installation Methods

### Method 1: Automatic Installation (Recommended)

1. **Copy the add-on to your Home Assistant**:
   ```bash
   # On your Home Assistant machine
   cd /path/to/schnell-home-automation
   cd custom_data_storage
   sudo ./install.sh
   ```

2. **The script will**:
   - Copy files to `/usr/share/hassio/addons/local/custom_data_storage`
   - Set proper permissions
   - Create data directory
   - Restart Home Assistant Supervisor

### Method 2: Manual Installation

1. **Copy add-on files**:
   ```bash
   sudo mkdir -p /usr/share/hassio/addons/local/custom_data_storage
   sudo cp -r custom_data_storage/* /usr/share/hassio/addons/local/custom_data_storage/
   sudo chmod +x /usr/share/hassio/addons/local/custom_data_storage/run.sh
   ```

2. **Restart Home Assistant Supervisor**:
   ```bash
   sudo systemctl restart hassio-supervisor
   ```

### Method 3: Development Installation

For development and testing:

1. **Create symbolic link**:
   ```bash
   sudo ln -s /path/to/your/project/custom_data_storage /usr/share/hassio/addons/local/custom_data_storage
   ```

2. **Restart supervisor**:
   ```bash
   sudo systemctl restart hassio-supervisor
   ```

## ⚙️ Configuration

### 1. Install the Add-on

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Click on **Local add-ons** section
3. Find **"Custom Data Storage"**
4. Click **INSTALL**

### 2. Configure the Add-on

Before starting, configure the add-on options:

```yaml
log_level: info                    # Log level (trace, debug, info, warning, error, fatal)
storage_path: /data/custom_storage # Storage directory path
max_storage_size_mb: 100          # Maximum storage size in MB
enable_websocket: true            # Enable WebSocket support
enable_cors: true                 # Enable CORS for web apps
api_key: ""                       # Optional API key for authentication
```

### 3. Start the Add-on

1. Click **START**
2. Enable **"Start on boot"** if desired
3. Enable **"Watchdog"** for automatic restart on crashes

## 🔧 Configuration Options Explained

### `log_level`
- **Options**: `trace`, `debug`, `info`, `warning`, `error`, `fatal`
- **Default**: `info`
- **Description**: Controls the verbosity of logs

### `storage_path`
- **Default**: `/data/custom_storage`
- **Description**: Directory where data files are stored
- **Note**: Must be within `/data/` for persistence

### `max_storage_size_mb`
- **Default**: `100`
- **Range**: 1-1000 MB
- **Description**: Maximum storage size limit

### `enable_websocket`
- **Default**: `true`
- **Description**: Enable WebSocket for real-time updates

### `enable_cors`
- **Default**: `true`
- **Description**: Enable CORS for web application access

### `api_key`
- **Default**: `""` (empty)
- **Description**: Optional API key for authentication
- **Example**: `"your-secret-api-key-here"`

## 🌐 Network Configuration

### Port Information
- **Custom Data Storage**: Port 8100
- **HA Data Collector**: Port 8099 (your existing add-on)
- **Home Assistant**: Port 8123 (default)

### Firewall Configuration
If you have a firewall, ensure port 8100 is accessible:

```bash
# UFW (Ubuntu)
sudo ufw allow 8100

# iptables
sudo iptables -A INPUT -p tcp --dport 8100 -j ACCEPT
```

## 🧪 Testing the Installation

### 1. Health Check
```bash
curl http://your-ha-ip:8100/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-22T10:30:15.123Z",
  "storage_size_mb": 0.0,
  "websocket_enabled": true
}
```

### 2. Store Test Data
```bash
curl -X POST http://your-ha-ip:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": "hello world", "category": "test"}'
```

### 3. Retrieve Test Data
```bash
curl http://your-ha-ip:8100/api/data/test/test
```

### 4. Run Comprehensive Tests
```bash
cd custom_data_storage
python3 test_addon.py http://your-ha-ip:8100
```

## 🔐 Security Configuration

### API Key Setup
1. **Generate a secure API key**:
   ```bash
   openssl rand -hex 32
   ```

2. **Set in add-on configuration**:
   ```yaml
   api_key: "your-generated-api-key-here"
   ```

3. **Use in API requests**:
   ```bash
   curl -H "X-API-Key: your-api-key" http://your-ha-ip:8100/api/data
   ```

### Network Security
- **Internal Network**: Recommended for internal use only
- **External Access**: Use reverse proxy with SSL if external access needed
- **VPN**: Consider VPN access for remote usage

## 📊 Monitoring and Maintenance

### 1. Check Add-on Status
- Go to **Settings** → **Add-ons** → **Custom Data Storage**
- Check **"Log"** tab for any errors
- Monitor **"Info"** tab for resource usage

### 2. Storage Monitoring
```bash
# Check storage usage
curl http://your-ha-ip:8100/api/metadata
```

### 3. Log Monitoring
```bash
# View add-on logs
docker logs addon_custom_data_storage
```

## 🔄 Backup and Restore

### Backup Data
```bash
# Backup storage directory
sudo tar -czf custom_data_backup_$(date +%Y%m%d).tar.gz /data/custom_storage/
```

### Restore Data
```bash
# Restore storage directory
sudo tar -xzf custom_data_backup_YYYYMMDD.tar.gz -C /
sudo chown -R root:root /data/custom_storage/
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Add-on Not Starting
- **Check logs**: Settings → Add-ons → Custom Data Storage → Log
- **Check configuration**: Ensure valid YAML syntax
- **Check permissions**: Ensure `/data/custom_storage` is writable

#### 2. Port 8100 Not Accessible
- **Check add-on status**: Ensure add-on is running
- **Check firewall**: Ensure port 8100 is open
- **Check network**: Ensure Home Assistant is accessible

#### 3. API Key Errors
- **Verify key**: Ensure API key matches configuration
- **Check headers**: Use `X-API-Key` header or `api_key` query parameter

#### 4. Storage Full
- **Check size**: Use `/api/metadata` endpoint
- **Increase limit**: Modify `max_storage_size_mb` in configuration
- **Clean data**: Delete unnecessary data

### Debug Mode
Enable debug logging:
```yaml
log_level: debug
```

### Reset Storage
To reset all data:
```bash
sudo rm -rf /data/custom_storage/*
# Restart the add-on
```

## 📱 Integration Examples

### Flutter Integration
See `flutter_integration_example.dart` for complete Flutter integration example.

### Basic API Usage
```bash
# Store user preference
curl -X POST http://192.168.1.100:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "theme", "value": "dark", "category": "user_preferences"}'

# Get user preference
curl http://192.168.1.100:8100/api/data/user_preferences/theme

# Store device properties
curl -X POST http://192.168.1.100:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "fan.living_room", "value": {"name": "Main Fan", "icon": "🌀"}, "category": "devices"}'
```

## 🎯 Next Steps

1. **Install and configure** the add-on
2. **Test basic functionality** with curl commands
3. **Integrate with your Flutter app** using the provided example
4. **Set up monitoring** and backup procedures
5. **Configure security** with API keys if needed

## 📞 Support

If you encounter issues:
1. Check the add-on logs
2. Verify configuration
3. Test with curl commands
4. Run the test script
5. Check network connectivity

The add-on is now ready to store and serve your custom home automation data! 🎉
