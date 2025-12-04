# Matter OTA Provider Add-on

This Home Assistant add-on provides a Matter OTA (Over-The-Air) Provider for firmware updates to Matter devices.

## Installation

1. Copy the `ha-ota-provider-addon` folder to your Home Assistant `addons` directory
2. Refresh the Add-on Store
3. Install the "Matter OTA Provider" add-on
4. Configure the add-on (see Configuration section)
5. Start the add-on

## Configuration

### Options

- **discriminator** (default: 3840): The discriminator for Matter commissioning
- **passcode** (default: 20202021): The passcode for Matter commissioning
- **port** (default: 5580): The port for the OTA provider service
- **ota_files_path** (default: "/share/ota-files"): Path where OTA firmware files are stored

### Example Configuration

```yaml
discriminator: 3840
passcode: 20202021
port: 5580
ota_files_path: "/share/ota-files"
```

## Usage

### 1. Commission the OTA Provider

After starting the add-on, commission it using the chip-tool API:

```bash
curl -X POST http://192.168.6.167:6000/ota/commission \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": 22,
    "setup_pin_code": 20202021,
    "discriminator": 3840
  }'
```

### 2. Set Access Control List (ACL)

Configure ACL to allow OTA requestors to access the provider:

```bash
curl -X POST http://192.168.6.167:6000/ota/set-acl \
  -H "Content-Type: application/json" \
  -d '{
    "provider_node_id": 22,
    "admin_node_id": 112233
  }'
```

### 3. Upload OTA Files

Place your OTA firmware files in the `/share/ota-files` directory. You can upload files via:

- Home Assistant File Editor add-on
- Samba Share add-on
- SSH/SCP

OTA files must have the Matter OTA image header. Use the `ota_image_tool.py` to create proper OTA images:

```bash
python3 ota_image_tool.py create \
  -v 0xFFF1 \
  -p 0x8001 \
  -vn 2 \
  -vs "2.0" \
  -da sha256 \
  firmware.bin \
  firmware.ota
```

### 4. Announce OTA Update

Use the chip-tool API or Flutter app to announce updates to devices:

```bash
curl -X POST http://192.168.6.167:6000/ota/announce \
  -H "Content-Type: application/json" \
  -d '{
    "device_node_id": 20,
    "provider_node_id": 22
  }'
```

Or use the command:

```bash
chip-tool otasoftwareupdaterequestor announce-otaprovider 22 0 0 0 20 0
```

Where:
- `22` is the OTA provider node ID
- `20` is the device (OTA requestor) node ID

## Troubleshooting

### Check Add-on Logs

View the add-on logs in Home Assistant to see if the OTA provider is running correctly.

### Verify OTA Files

Ensure your OTA files:
- Are placed in `/share/ota-files`
- Have the correct Matter OTA image header
- Match the vendor ID and product ID of your devices

### Network Issues

- The add-on uses `host_network: true` to ensure proper Matter communication
- Ensure your Home Assistant instance can communicate with Matter devices on the same network

## Support

For issues and questions:
- Check the add-on logs
- Verify your configuration
- Ensure OTA files are properly formatted

## Version History

### 1.0.0
- Initial release
- Basic OTA provider functionality
- Support for firmware file serving
- Matter commissioning support

