#!/bin/bash

echo "🔍 Home Assistant Addon Verification Script"
echo "==========================================="
echo ""

# Check if required files exist
echo "📋 Checking required files..."
files=("config.json" "config.yaml" "Dockerfile" "run.sh" "build.yaml")
all_present=true

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file - Found"
    else
        echo "❌ $file - Missing"
        all_present=false
    fi
done

echo ""

# Check app directory
if [ -d "app" ]; then
    echo "✅ app/ directory - Found"
    echo "   Files in app/:"
    ls -la app/ | grep "\.py$" | awk '{print "   - " $9}'
else
    echo "❌ app/ directory - Missing"
    all_present=false
fi

echo ""

# Validate config.json
echo "🔍 Validating config.json..."
if command -v python3 &> /dev/null; then
    python3 -c "import json; json.load(open('config.json'))" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ config.json is valid JSON"
        
        # Extract key fields
        name=$(python3 -c "import json; print(json.load(open('config.json'))['name'])")
        slug=$(python3 -c "import json; print(json.load(open('config.json'))['slug'])")
        version=$(python3 -c "import json; print(json.load(open('config.json'))['version'])")
        
        echo "   Name: $name"
        echo "   Slug: $slug"
        echo "   Version: $version"
    else
        echo "❌ config.json has JSON syntax errors"
        all_present=false
    fi
else
    echo "⚠️  Python3 not found, skipping JSON validation"
fi

echo ""

# Check run.sh permissions
if [ -f "run.sh" ]; then
    if [ -x "run.sh" ]; then
        echo "✅ run.sh is executable"
    else
        echo "⚠️  run.sh is not executable (will be fixed during build)"
    fi
fi

echo ""
echo "==========================================="

if [ "$all_present" = true ]; then
    echo "✅ All required files are present!"
    echo ""
    echo "📦 Installation Instructions:"
    echo ""
    echo "1. Copy this entire directory to Home Assistant:"
    echo "   - For HA OS: /usr/share/hassio/addons/local/custom_data_storage/"
    echo "   - For HA Supervised: /addons/custom_data_storage/"
    echo "   - For HA Container: <config>/addons/custom_data_storage/"
    echo ""
    echo "2. Restart Home Assistant Supervisor:"
    echo "   ha supervisor reload"
    echo "   OR"
    echo "   Settings → Add-ons → ⋮ → Reload"
    echo ""
    echo "3. Check for the addon in:"
    echo "   Settings → Add-ons → Add-on Store → Local add-ons"
    echo ""
    echo "🔧 If addon still doesn't appear, check supervisor logs:"
    echo "   ha supervisor logs"
else
    echo "❌ Some required files are missing!"
    echo "   Please ensure all files are present before installation."
fi

echo ""
