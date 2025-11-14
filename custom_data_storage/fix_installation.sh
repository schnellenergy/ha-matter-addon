#!/bin/bash

echo "🔧 Custom Data Storage Add-on - Installation Fixer"
echo "=================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "config.yaml" ]; then
    echo "❌ Error: config.yaml not found!"
    echo "   Please run this script from the custom_data_storage directory"
    exit 1
fi

echo "✅ Found config.yaml"

# Remove duplicate config.json if it exists
if [ -f "config.json" ]; then
    echo "⚠️  Found duplicate config.json - removing it..."
    rm -f config.json
    echo "✅ Removed config.json"
else
    echo "✅ No duplicate config.json found"
fi

# Check for required files
echo ""
echo "📋 Checking required files..."
REQUIRED_FILES=("config.yaml" "Dockerfile" "build.yaml" "run.sh" "README.md")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file - MISSING!"
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo ""
    echo "❌ Missing required files: ${MISSING_FILES[*]}"
    echo "   Cannot proceed with installation"
    exit 1
fi

# Make run.sh executable
echo ""
echo "🔧 Setting permissions..."
chmod +x run.sh
chmod 644 config.yaml
chmod 644 Dockerfile
chmod 644 build.yaml
echo "✅ Permissions set"

# Check YAML syntax
echo ""
echo "🔍 Validating config.yaml..."
if command -v python3 &> /dev/null; then
    python3 -c "import yaml; yaml.safe_load(open('config.yaml'))" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ config.yaml is valid"
    else
        echo "❌ config.yaml has syntax errors!"
        echo "   Please check the YAML formatting"
        exit 1
    fi
else
    echo "⚠️  Python3 not found, skipping YAML validation"
fi

# Check slug matches folder name
SLUG=$(grep "^slug:" config.yaml | awk '{print $2}' | tr -d '"' | tr -d "'")
CURRENT_DIR=$(basename "$PWD")

echo ""
echo "🔍 Checking folder name..."
echo "  Slug in config.yaml: $SLUG"
echo "  Current folder name: $CURRENT_DIR"

if [ "$SLUG" != "$CURRENT_DIR" ]; then
    echo "⚠️  WARNING: Folder name doesn't match slug!"
    echo "   Folder should be named: $SLUG"
    echo "   Current folder name: $CURRENT_DIR"
    echo ""
    echo "   This might prevent the add-on from showing up."
else
    echo "✅ Folder name matches slug"
fi

# Summary
echo ""
echo "=================================================="
echo "✅ Installation check complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Copy this folder to /addon/local/ on your Home Assistant"
echo "   2. Via Samba: Copy to \\\\homeassistant.local\\addon\\local\\"
echo "   3. Reload add-ons: Settings → Add-ons → ⋮ → Reload"
echo "   4. Look for 'Custom Data Storage' in Local add-ons"
echo ""
echo "🔍 If add-on doesn't appear, check supervisor logs:"
echo "   ha supervisor logs | grep -i custom_data_storage"
echo "=================================================="

