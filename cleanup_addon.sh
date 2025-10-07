#!/bin/bash
# Wifi Onboarding Addon Cleanup Script
# Removes unnecessary development, test, and debug files

set -e

echo "🧹 CLEANING UP WIFI ONBOARDING ADDON FOLDER"
echo "============================================="

cd "$(dirname "$0")"

# List files to keep (essential for addon functionality)
KEEP_PYTHON_FILES=(
    "improved_ble_service.py"
    "button_monitor.py" 
    "led_controller.py"
    "ble_diagnostics.py"
    "device_diagnostics.py"
    "gpio_test.py"
    "simple_gpio_test.py"
    "permission_test.py"
    "gpio_cleanup.py"
)

KEEP_SCRIPTS_CONFIGS=(
    "run.sh"
    "config.json"
    "Dockerfile" 
    "gpio_setup.sh"
)

KEEP_MD_FILES=(
    "RASPBERRY_PI_5_DEPLOYMENT.md"
    "README.md"
)

# Create backup directory
echo "[INFO] Creating backup directory..."
mkdir -p ./cleanup_backup
BACKUP_DIR="./cleanup_backup/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[INFO] Files to be removed will be backed up to: $BACKUP_DIR"

# Function to check if file should be kept
should_keep() {
    local file="$1"
    
    # Keep essential Python files
    for keep_file in "${KEEP_PYTHON_FILES[@]}"; do
        if [ "$file" = "$keep_file" ]; then
            return 0
        fi
    done
    
    # Keep essential scripts and configs
    for keep_file in "${KEEP_SCRIPTS_CONFIGS[@]}"; do
        if [ "$file" = "$keep_file" ]; then
            return 0
        fi
    done
    
    # Keep important MD files
    for keep_file in "${KEEP_MD_FILES[@]}"; do
        if [ "$file" = "$keep_file" ]; then
            return 0
        fi
    done
    
    return 1
}

# Remove unnecessary files
echo ""
echo "🗑️ REMOVING UNNECESSARY FILES:"
echo "=============================="

removed_count=0
kept_count=0

for file in *; do
    # Skip directories and hidden files
    if [ -d "$file" ] || [[ "$file" == .* ]]; then
        continue
    fi
    
    if should_keep "$file"; then
        echo "✅ KEEP: $file"
        ((kept_count++))
    else
        echo "🗑️ REMOVE: $file"
        cp "$file" "$BACKUP_DIR/" 2>/dev/null || true
        rm -f "$file"
        ((removed_count++))
    fi
done

# Handle directories
echo ""
echo "📁 CHECKING DIRECTORIES:"
echo "========================"

# Keep "refer only" directory if it exists
if [ -d "refer only" ]; then
    echo "✅ KEEP: refer only/ (reference implementation)"
    cp -r "refer only" "$BACKUP_DIR/" 2>/dev/null || true
else
    echo "ℹ️ No 'refer only' directory found"
fi

# Remove any other development directories except backup
for dir in */; do
    if [[ "$dir" == "cleanup_backup/" ]]; then
        continue
    fi
    if [[ "$dir" == "refer only/" ]]; then
        echo "✅ KEEP: $dir"
        continue
    fi
    echo "🗑️ REMOVE: $dir"
    cp -r "$dir" "$BACKUP_DIR/" 2>/dev/null || true
    rm -rf "$dir"
    ((removed_count++))
done

echo ""
echo "✅ CLEANUP COMPLETE!"
echo "==================="
echo "📊 Files kept: $kept_count"
echo "🗑️ Files removed: $removed_count"
echo "💾 Backup location: $BACKUP_DIR"
echo ""
echo "🎯 FINAL ADDON STRUCTURE:"
echo "========================"
ls -la | grep -v '^total' | head -20

echo ""
echo "✅ Addon folder cleaned up successfully!"
echo "📦 Only essential files remain for addon functionality"
