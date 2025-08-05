# WiFi Onboarding Home Assistant Add-on

A comprehensive Home Assistant add-on that provides WiFi onboarding through a captive portal. This add-on creates a temporary WiFi hotspot, allows devices to connect and configure WiFi credentials via a web interface, then automatically connects to the specified network.

## 🚀 Features

- **Captive Portal**: Automatic redirection to configuration page on connection
- **Multi-Platform Support**: Works with Android, iOS, Windows, macOS, and Linux devices
- **GPIO Reset Button**: Physical reset functionality with Raspberry Pi 5 compatibility
- **Dual Network Mode**: Maintains Ethernet connection while configuring WiFi
- **Static IP Support**: Optional static IP configuration for connected networks
- **Robust Connection Logic**: Multiple fallback mechanisms for reliable WiFi connection
- **Enhanced Monitoring**: Real-time status monitoring and debugging endpoints

## 📋 Specifications

### System Requirements

- **Home Assistant OS**: Compatible with Home Assistant OS/Supervised
- **Architecture Support**: `aarch64`, `armhf`, `armv7`, `amd64`, `i386`
- **Hardware**: Raspberry Pi with WiFi capability (tested on Pi 4/5)
- **GPIO**: Optional physical reset button support

### Network Configuration

- **Hotspot SSID**: Configurable (default: "SMASH-Hub")
- **Hotspot IP Range**: 192.168.4.1/24 (192.168.4.10-192.168.4.50 DHCP pool)
- **Web Interface**: HTTP on port 80 (http://192.168.4.1)
- **DNS Redirection**: Comprehensive captive portal detection for all major platforms

### Key Technical Specifications

```json
{
  "privileges": ["NET_ADMIN", "SYS_MODULE", "SYS_RAWIO", "SYS_ADMIN", "NET_RAW"],
  "network_mode": "host",
  "gpio_devices": ["/dev/gpiomem", "/dev/gpiochip0-4", "/dev/mem"],
  "timeout": 300,
  "connection_timeout": "60s (configurable 30-300s)",
  "button_hold_time": "5s (configurable 3-30s)"
}
```

## 🔧 Configuration Options

### Add-on Configuration

```yaml
debug: false                    # Enable debug logging
gpio_pin: 17                   # GPIO pin for reset button (1-40)
hold_time: 5                   # Button hold time in seconds (3-30)
hotspot_ssid: "SMASH-Hub"      # WiFi hotspot name
hotspot_channel: 6             # WiFi channel (1-13)
enable_button: true            # Enable GPIO button monitoring
auto_reboot: true              # Auto reboot after successful connection
connection_timeout: 60         # WiFi connection timeout (30-300s)
use_static_ip: false           # Use static IP instead of DHCP
static_ip: "192.168.1.100"     # Static IP address
static_gateway: "192.168.1.1"  # Static gateway
static_dns: "8.8.8.8"          # Static DNS server
dual_network: true             # Enable dual network mode
```

## 🏗️ Architecture

### Core Components

#### 1. Flask Web Application (`onboarding.py`)
```python
class WorkingWiFiController:
    # Main controller managing WiFi operations
    # Features: captive portal, connection logic, status monitoring
```

**Key Endpoints:**
- `/` - Main configuration interface
- `/generate_204` - Android captive portal detection
- `/connectivitycheck.gstatic.com/generate_204` - Android connectivity check
- `/hotspot-detect.html` - Apple captive portal detection
- `/status` - Real-time system status API
- `/debug` - Detailed diagnostic information
- `/reset` - Configuration reset API

#### 2. GPIO Button Monitor (`button_monitor.py`)
```python
class ButtonMonitor:
    # Multi-library GPIO support with Pi 5 compatibility
    # Libraries: lgpio, gpiozero, RPi.GPIO, python-periphery
```

**Features:**
- Automatic GPIO library detection and fallback
- Pi 5 kernel 6.6+ compatibility with pin offset handling
- Debouncing and hold-time validation
- Safe reset with network state preservation

#### 3. Service Orchestrator (`run.sh`)
```bash
# Coordinated service management:
# - hostapd (WiFi Access Point)
# - dnsmasq (DHCP/DNS server)
# - Flask web server
# - GPIO button monitor
```

### Network Operation Modes

#### Hotspot Mode (Default)
```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│   Device    │◄──►│ WiFi Hotspot │◄──►│ Captive Portal  │
│ (Phone/PC)  │    │ (192.168.4.1)│    │ (Flask Server)  │
└─────────────┘    └──────────────┘    └─────────────────┘
```

#### Client Mode (After Configuration)
```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Home Router │◄──►│ Raspberry Pi │◄──►│ Home Assistant  │
│   (WiFi)    │    │  (wlan0)     │    │    (Local)      │
└─────────────┘    └──────────────┘    └─────────────────┘
```

## 🔌 Installation

### Home Assistant Add-on Store

1. Add this repository to Home Assistant:
   ```
   Settings → Add-ons → Add-on Store → ⋮ → Repositories
   ```

2. Install the "WiFi Onboarding" add-on

3. Configure options in the add-on configuration tab

4. Start the add-on

### Manual Installation

```bash
# Clone repository
git clone https://github.com/yourusername/wifi_onboarding.git
cd wifi_onboarding

# Build Docker image
docker build -t wifi-onboarding .

# Run with required privileges
docker run --privileged --network host \
  -v /data:/data \
  -e HOTSPOT_SSID="WiFi-Setup" \
  wifi-onboarding
```

## 🚀 Usage

### Initial Setup

1. **Start Add-on**: The system creates a WiFi hotspot "SMASH-Hub" (or configured name)

2. **Connect Device**: Connect phone/laptop to the hotspot (no password required)

3. **Configure WiFi**: Browser automatically opens to configuration page at `http://192.168.4.1`

4. **Enter Credentials**: Input target WiFi network SSID and password

5. **Auto-Connect**: System automatically connects to WiFi and saves configuration

### Reset Methods

#### Physical Button Reset
```python
# GPIO pin 17 (configurable)
# Hold for 5+ seconds to reset configuration
```

#### API Reset
```bash
curl -X POST http://192.168.4.1/reset
```

#### Manual Reset
```bash
# Create reset flag file
touch /tmp/wifi_reset
```

### Dual Network Mode

When Ethernet is connected during reset:
```
Ethernet: 192.168.3.120:8123 (Home Assistant)
WiFi Hotspot: 192.168.4.1 (Configuration)
```

## 🔍 Monitoring & Debugging

### Status Monitoring

```bash
# Real-time system status
curl http://192.168.4.1/status | jq

# Detailed diagnostics
curl http://192.168.4.1/debug | jq
```

### Log Analysis

```bash
# Container logs
docker logs <container_id> --follow

# DNS query monitoring
tail -f /tmp/dnsmasq.log

# Service status
ps aux | grep -E "(hostapd|dnsmasq|wpa_supplicant)"
```

### Testing Commands

```bash
# Test GPIO button functionality
python3 button_monitor.py --pin 17 --test --debug

# Test network connectivity
ping -c 3 8.8.8.8

# Validate WiFi configuration
jq . /data/wifi_config.json

# Test captive portal endpoints
curl -v http://192.168.4.1/generate_204
```

## 🛠️ Development

### Project Structure

```
wifi_onboarding/
├── onboarding.py          # Main Flask application
├── button_monitor.py      # GPIO button handling
├── run.sh                 # Service orchestrator
├── config.json           # Home Assistant add-on config
├── Dockerfile            # Container configuration
├── dnsmasq.conf          # DNS/DHCP server config
└── CLAUDE.md             # Development documentation
```

### Key Code Snippets

#### WiFi Connection Logic
```python
def connect_to_wifi(self, ssid, password):
    """Robust WiFi connection with multiple fallback mechanisms"""
    try:
        # 1. Stop hotspot services
        self.stop_hotspot()
        
        # 2. Reset network interface
        self.reset_interface()
        
        # 3. Configure wpa_supplicant
        self.setup_wpa_supplicant(ssid, password)
        
        # 4. Start DHCP client with fallback
        self.start_dhcp_client()
        
        # 5. Verify connectivity
        return self.verify_connection()
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return False
```

#### GPIO Button Handling
```python
def setup_gpio(self):
    """Multi-library GPIO setup with Pi 5 compatibility"""
    libraries = ['lgpio', 'gpiozero', 'RPi.GPIO', 'periphery']
    
    for lib in libraries:
        try:
            return self.init_gpio_library(lib)
        except Exception as e:
            logger.warning(f"{lib} failed: {e}")
    
    raise Exception("No GPIO library available")
```

#### Captive Portal Detection
```python
@app.route('/generate_204')
@app.route('/connectivitycheck.gstatic.com/generate_204')
@app.route('/hotspot-detect.html')
def captive_portal_detection():
    """Multi-platform captive portal detection"""
    return redirect('/')
```

### Environment Variables

```bash
# Core configuration
HOTSPOT_SSID="WiFi-Setup"     # Hotspot network name
GPIO_PIN=17                   # Reset button pin
HOLD_TIME=5                   # Button hold duration
CONNECTION_TIMEOUT=60         # WiFi connection timeout
DEBUG=false                   # Debug logging
ENABLE_BUTTON=true            # Enable GPIO monitoring
AUTO_REBOOT=true              # Auto reboot after connection

# Network configuration
USE_STATIC_IP=false           # Enable static IP
STATIC_IP="192.168.1.100"     # Static IP address
STATIC_GATEWAY="192.168.1.1"  # Static gateway
STATIC_DNS="8.8.8.8"          # Static DNS server
DUAL_NETWORK=true             # Dual network mode
```

## 🔒 Security

### Required Privileges

```json
{
  "privileged": [
    "NET_ADMIN",    # Network interface management
    "SYS_MODULE",   # Kernel module loading
    "SYS_RAWIO",    # Raw I/O access
    "SYS_ADMIN",    # System administration
    "NET_RAW"       # Raw network access
  ],
  "devices": [
    "/dev/gpiomem",     # GPIO memory access
    "/dev/gpiochip0-4", # GPIO chip devices
    "/dev/mem"          # System memory access
  ]
}
```

### Network Security

- **Temporary Hotspot**: Hotspot is disabled after successful WiFi connection
- **No Password Storage**: WiFi passwords are not logged or exposed in APIs
- **Local Operation**: All configuration happens locally, no external communication
- **Secure Reset**: Physical button prevents unauthorized remote resets

## 🐛 Troubleshooting

### Common Issues

#### Pi 5 GPIO Problems
```bash
# Test GPIO functionality
python3 button_monitor.py --pin 17 --test

# Check GPIO libraries
pip list | grep -i gpio
```

#### Captive Portal Not Working
```bash
# Check DNS redirection
tail -f /tmp/dnsmasq.log

# Test platform endpoints
curl -v http://192.168.4.1/generate_204
```

#### WiFi Connection Failures
```bash
# Check connection status
curl http://192.168.4.1/status | jq '.wifi_status'

# Monitor DHCP process
ps aux | grep dhcp
```

#### Service Conflicts
```bash
# Check running services
ps aux | grep -E "(hostapd|wpa_supplicant|dnsmasq)"

# Kill conflicting processes
pkill hostapd && pkill wpa_supplicant
```

### Recovery Procedures

#### Full Reset
```bash
# Stop all services
./run.sh stop

# Clear configuration
rm -f /data/wifi_config.json
rm -f /tmp/wifi_*

# Restart services
./run.sh
```

#### Network Interface Reset
```bash
# Reset wlan0 interface
ip link set wlan0 down
ip addr flush dev wlan0
ip link set wlan0 up
```

## 📝 File Locations

```bash
# Persistent storage
/data/wifi_config.json          # Saved WiFi credentials
/data/options.json              # Home Assistant add-on options

# Temporary files
/tmp/wpa_supplicant.conf        # wpa_supplicant configuration
/tmp/hostapd.conf               # hostapd configuration
/tmp/wifi_reset                 # Reset flag
/tmp/wifi_state.json            # Runtime state
/tmp/dnsmasq.log               # DNS query logs

# System files
/sys/class/net/wlan0/           # Network interface status
/proc/net/wireless              # Wireless interface info
```

### Code Standards

- **Python**: PEP 8 compliance
- **Bash**: ShellCheck validation
- **Docker**: Multi-stage builds for optimization
- **Documentation**: Comprehensive inline comments
- **Logging**: Structured logging with appropriate levels

