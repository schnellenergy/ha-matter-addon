#!/bin/bash

echo "🔍 Home Assistant Add-on Diagnostic Tool"
echo "=========================================="
echo ""
echo "This script should be run via SSH on your Home Assistant"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Home Assistant
if ! command -v ha &> /dev/null; then
    echo -e "${RED}❌ Error: 'ha' command not found!${NC}"
    echo "   This script must be run on Home Assistant via SSH"
    exit 1
fi

echo -e "${GREEN}✅ Running on Home Assistant${NC}"
echo ""

# Check if add-on folder exists
ADDON_PATH="/addon/local/custom_data_storage"
echo "🔍 Checking add-on location..."
if [ -d "$ADDON_PATH" ]; then
    echo -e "${GREEN}✅ Add-on folder exists at $ADDON_PATH${NC}"
else
    echo -e "${RED}❌ Add-on folder NOT found at $ADDON_PATH${NC}"
    echo ""
    echo "Available folders in /addon/local/:"
    ls -la /addon/local/ 2>/dev/null || echo "  (directory doesn't exist or is empty)"
    exit 1
fi

# Check required files
echo ""
echo "📋 Checking required files..."
cd "$ADDON_PATH" || exit 1

REQUIRED_FILES=("config.yaml" "Dockerfile" "build.yaml" "run.sh" "README.md")
ALL_PRESENT=true

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}✅${NC} $file"
    else
        echo -e "  ${RED}❌${NC} $file - MISSING!"
        ALL_PRESENT=false
    fi
done

if [ "$ALL_PRESENT" = false ]; then
    echo -e "${RED}❌ Some required files are missing!${NC}"
    exit 1
fi

# Check for duplicate config.json
echo ""
echo "🔍 Checking for duplicate config files..."
if [ -f "config.json" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Found config.json (should only have config.yaml)${NC}"
    echo "   Removing config.json..."
    rm -f config.json
    echo -e "${GREEN}✅ Removed config.json${NC}"
else
    echo -e "${GREEN}✅ No duplicate config.json${NC}"
fi

# Check file permissions
echo ""
echo "🔍 Checking file permissions..."
if [ -x "run.sh" ]; then
    echo -e "${GREEN}✅ run.sh is executable${NC}"
else
    echo -e "${YELLOW}⚠️  run.sh is not executable - fixing...${NC}"
    chmod +x run.sh
    echo -e "${GREEN}✅ Fixed run.sh permissions${NC}"
fi

# Validate config.yaml
echo ""
echo "🔍 Validating config.yaml..."
if command -v python3 &> /dev/null; then
    python3 -c "import yaml; yaml.safe_load(open('config.yaml'))" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ config.yaml is valid YAML${NC}"
    else
        echo -e "${RED}❌ config.yaml has syntax errors!${NC}"
        python3 -c "import yaml; yaml.safe_load(open('config.yaml'))" 2>&1
        exit 1
    fi
fi

# Show config.yaml slug
SLUG=$(grep "^slug:" config.yaml | awk '{print $2}' | tr -d '"' | tr -d "'")
echo ""
echo "📝 Add-on configuration:"
echo "   Slug: $SLUG"
echo "   Folder: $(basename "$PWD")"

# Check supervisor logs for errors
echo ""
echo "🔍 Checking supervisor logs for errors..."
echo "   (Last 50 lines related to custom_data_storage)"
ha supervisor logs 2>/dev/null | grep -i "custom_data_storage" | tail -50 || echo "   No logs found"

# Reload supervisor
echo ""
echo "🔄 Reloading Home Assistant Supervisor..."
ha supervisor reload
sleep 3

# Check if add-on is now visible
echo ""
echo "🔍 Checking if add-on is registered..."
ha addons 2>/dev/null | grep -i "custom" || echo "   Add-on not found in list"

echo ""
echo "=========================================="
echo "✅ Diagnostic complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Go to Settings → Add-ons in Home Assistant"
echo "   2. Click the three dots (⋮) in top right"
echo "   3. Click 'Reload'"
echo "   4. Check 'Local add-ons' section"
echo ""
echo "🔍 If still not showing, check the supervisor logs above for errors"
echo "=========================================="

