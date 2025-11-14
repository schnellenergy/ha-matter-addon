#!/bin/bash

# Schnell Custom Metrics Add-on Installation Script
# This script helps install the add-on on Home Assistant OS

set -e

echo "🏠 Schnell Custom Metrics Add-on Installation Script"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running on Home Assistant OS
check_ha_os() {
    if [ ! -f "/etc/os-release" ]; then
        print_error "Cannot determine OS. This script is designed for Home Assistant OS."
        exit 1
    fi
    
    if ! grep -q "Home Assistant" /etc/os-release; then
        print_warning "This doesn't appear to be Home Assistant OS. Continuing anyway..."
    else
        print_status "Running on Home Assistant OS"
    fi
}

# Check if we have the necessary files
check_files() {
    print_step "Checking required files..."
    
    required_files=(
        "config.yaml"
        "Dockerfile"
        "run.sh"
        "app/main.py"
        "app/database.py"
        "app/models.py"
        "app/routes.py"
        "app/websocket_handler.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file missing: $file"
            exit 1
        fi
    done
    
    print_status "All required files found"
}

# Create add-on directory
create_addon_directory() {
    print_step "Creating add-on directory..."
    
    ADDON_DIR="/addons/schnell_custom_metrics"
    
    if [ -d "$ADDON_DIR" ]; then
        print_warning "Add-on directory already exists. Backing up..."
        mv "$ADDON_DIR" "${ADDON_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    fi
    
    mkdir -p "$ADDON_DIR"
    print_status "Created directory: $ADDON_DIR"
}

# Copy files
copy_files() {
    print_step "Copying add-on files..."
    
    ADDON_DIR="/addons/schnell_custom_metrics"
    
    # Copy all files to the add-on directory
    cp -r . "$ADDON_DIR/"
    
    # Set proper permissions
    chmod +x "$ADDON_DIR/run.sh"
    chmod +x "$ADDON_DIR/install.sh"
    
    print_status "Files copied successfully"
}

# Create data directories
create_data_dirs() {
    print_step "Creating data directories..."
    
    DATA_DIR="/data/schnell_custom_metrics"
    mkdir -p "$DATA_DIR/db"
    mkdir -p "$DATA_DIR/backups"
    mkdir -p "$DATA_DIR/logs"
    
    # Set permissions
    chmod 755 "$DATA_DIR"
    chmod 755 "$DATA_DIR/db"
    chmod 755 "$DATA_DIR/backups"
    chmod 755 "$DATA_DIR/logs"
    
    print_status "Data directories created"
}

# Generate sample configuration
generate_sample_config() {
    print_step "Generating sample configuration..."
    
    cat > /tmp/schnell_metrics_config.yaml << 'EOF'
# Schnell Custom Metrics Add-on Configuration
# Copy this to your add-on configuration in Home Assistant

log_level: info
ha_token: "YOUR_LONG_LIVED_ACCESS_TOKEN_HERE"
auto_backup: true
backup_interval_hours: 24

# To get a Long-Lived Access Token:
# 1. Go to your Home Assistant Profile
# 2. Scroll down to "Long-Lived Access Tokens"
# 3. Click "Create Token"
# 4. Give it a name like "Schnell Metrics Add-on"
# 5. Copy the token and replace YOUR_LONG_LIVED_ACCESS_TOKEN_HERE above
EOF
    
    print_status "Sample configuration saved to /tmp/schnell_metrics_config.yaml"
}

# Test installation
test_installation() {
    print_step "Testing installation..."
    
    ADDON_DIR="/addons/schnell_custom_metrics"
    
    # Check if all files are in place
    if [ -f "$ADDON_DIR/config.yaml" ] && [ -f "$ADDON_DIR/Dockerfile" ] && [ -x "$ADDON_DIR/run.sh" ]; then
        print_status "Installation test passed"
        return 0
    else
        print_error "Installation test failed"
        return 1
    fi
}

# Main installation function
main() {
    echo
    print_step "Starting installation process..."
    
    # Run checks and installation steps
    check_ha_os
    check_files
    create_addon_directory
    copy_files
    create_data_dirs
    generate_sample_config
    
    if test_installation; then
        echo
        print_status "✅ Installation completed successfully!"
        echo
        echo "Next steps:"
        echo "1. Go to Home Assistant Settings → Add-ons → Add-on Store"
        echo "2. Click ⋮ (three dots) → Repositories"
        echo "3. Add local repository: /addons/schnell_custom_metrics"
        echo "4. Find 'Schnell Custom Metrics Add-on' and click Install"
        echo "5. Configure the add-on with your settings"
        echo "6. Start the add-on"
        echo
        echo "Sample configuration is available at: /tmp/schnell_metrics_config.yaml"
        echo
        echo "API will be available at: http://homeassistant.local:8080"
        echo "Documentation: http://homeassistant.local:8080/docs"
        echo
    else
        print_error "❌ Installation failed!"
        exit 1
    fi
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Schnell Custom Metrics Add-on Installation Script"
        echo
        echo "Usage: $0 [OPTIONS]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --check        Only check requirements, don't install"
        echo "  --uninstall    Remove the add-on"
        echo
        echo "This script must be run from the directory containing the add-on files."
        exit 0
        ;;
    --check)
        print_step "Checking requirements only..."
        check_ha_os
        check_files
        print_status "✅ All checks passed!"
        exit 0
        ;;
    --uninstall)
        print_step "Uninstalling Schnell Custom Metrics Add-on..."
        
        if [ -d "/addons/schnell_custom_metrics" ]; then
            rm -rf "/addons/schnell_custom_metrics"
            print_status "Add-on directory removed"
        fi
        
        print_warning "Data directory /data/schnell_custom_metrics preserved"
        print_warning "Remove manually if you want to delete all data"
        
        print_status "✅ Uninstallation completed!"
        exit 0
        ;;
    "")
        # No arguments, run main installation
        main
        ;;
    *)
        print_error "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
