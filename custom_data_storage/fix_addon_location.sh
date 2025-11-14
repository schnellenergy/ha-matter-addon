#!/bin/bash

echo "🔧 Fixing Custom Data Storage Addon Location..."
echo "=============================================="
echo ""

# Check if source exists
if [ ! -d "/config/addons/local/custom_data_storage" ]; then
    echo "❌ Source not found: /config/addons/local/custom_data_storage"
    echo ""
    echo "Please ensure you copied the addon via Samba first!"
    echo "The folder should be visible in Samba at: addons/local/custom_data_storage"
    exit 1
fi

echo "✅ Found addon in Samba location"
echo ""

# Create target directory
echo "📁 Creating /addons/custom_data_storage..."
mkdir -p /addons/custom_data_storage

# Copy files
echo "📋 Copying files to correct location..."
cp -r /config/addons/local/custom_data_storage/* /addons/custom_data_storage/

# Set permissions
echo "🔐 Setting permissions..."
chmod +x /addons/custom_data_storage/run.sh

echo ""
echo "✅ Verifying installation..."

# Verify critical files
files_ok=true

if [ -f "/addons/custom_data_storage/config.json" ]; then
    echo "   ✅ config.json"
else
    echo "   ❌ config.json not found!"
    files_ok=false
fi

if [ -f "/addons/custom_data_storage/Dockerfile" ]; then
    echo "   ✅ Dockerfile"
else
    echo "   ❌ Dockerfile not found!"
    files_ok=false
fi

if [ -f "/addons/custom_data_storage/run.sh" ]; then
    echo "   ✅ run.sh"
else
    echo "   ❌ run.sh not found!"
    files_ok=false
fi

if [ -d "/addons/custom_data_storage/app" ]; then
    echo "   ✅ app/ directory"
else
    echo "   ❌ app/ directory not found!"
    files_ok=false
fi

echo ""

if [ "$files_ok" = false ]; then
    echo "❌ Some files are missing! Installation may not work."
    exit 1
fi

# Reload supervisor
echo "🔄 Reloading Home Assistant Supervisor..."
ha supervisor reload

if [ $? -eq 0 ]; then
    echo ""
    echo "=============================================="
    echo "✅ Installation Complete!"
    echo "=============================================="
    echo ""
    echo "📍 Addon installed at: /addons/custom_data_storage"
    echo ""
    echo "⏳ Wait 30-60 seconds, then check:"
    echo "   Settings → Add-ons → Add-on Store → Local add-ons"
    echo ""
    echo "🔍 Look for: 'Custom Data Storage'"
    echo ""
    echo "📝 If still not showing, check logs:"
    echo "   ha supervisor logs"
else
    echo ""
    echo "⚠️  Could not reload supervisor automatically."
    echo "Please reload manually:"
    echo "   Settings → Add-ons → ⋮ → Reload"
fi

echo ""
