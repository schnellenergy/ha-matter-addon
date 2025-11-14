#!/bin/bash

# Custom Data Storage Add-on Installation Script
# This script installs the Custom Data Storage add-on to Home Assistant

set -e

echo "🚀 Installing Custom Data Storage Add-on..."

# Configuration
ADDON_NAME="custom_data_storage"
HA_ADDONS_DIR="/usr/share/hassio/addons/local"
ADDON_DIR="$HA_ADDONS_DIR/$ADDON_NAME"

# Check if running on Home Assistant OS
if [ ! -d "/usr/share/hassio" ]; then
    echo "❌ This script must be run on Home Assistant OS"
    echo "📋 For other installations, manually copy the addon to your addons directory"
    exit 1
fi

# Create addon directory
echo "📁 Creating addon directory..."
sudo mkdir -p "$ADDON_DIR"

# Copy addon files
echo "📋 Copying addon files..."
sudo cp -r ./* "$ADDON_DIR/"

# Set permissions
echo "🔐 Setting permissions..."
sudo chmod +x "$ADDON_DIR/run.sh"
sudo chmod 644 "$ADDON_DIR/config.yaml"
sudo chmod 644 "$ADDON_DIR/Dockerfile"
sudo chmod 644 "$ADDON_DIR/build.yaml"

# Create data directory
echo "💾 Creating data directory..."
sudo mkdir -p "/data/custom_storage"
sudo chmod 755 "/data/custom_storage"

# Restart Home Assistant Supervisor to detect new addon
echo "🔄 Restarting Home Assistant Supervisor..."
sudo systemctl restart hassio-supervisor

echo "✅ Custom Data Storage Add-on installed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Go to Home Assistant → Settings → Add-ons"
echo "2. Find 'Custom Data Storage' in the Local add-ons section"
echo "3. Click on it and press 'INSTALL'"
echo "4. Configure the addon options if needed"
echo "5. Start the addon"
echo ""
echo "🌐 The addon will be available at: http://your-ha-ip:8100"
echo "📚 API Documentation: http://your-ha-ip:8100/api/metadata"
echo ""
echo "🔧 Default configuration:"
echo "   - Port: 8100"
echo "   - Storage path: /data/custom_storage"
echo "   - Max storage: 100MB"
echo "   - WebSocket: Enabled"
echo "   - CORS: Enabled"
echo "   - API Key: Not set (optional)"
