# Matter Controller Add-on for Home Assistant

This add-on provides a custom Matter controller that allows commissioning Matter devices from external applications and integrating them with Home Assistant.

## How It Works

This add-on uses the Home Assistant Matter Server as a foundation and adds a custom API layer on top of it. The Matter Server handles the low-level communication with Matter devices, while our API provides additional features like analytics, logging, and a more comprehensive REST API for external applications.

The add-on runs two services:
1. The Matter Server on port 5580 (internal)
2. Our custom API on port 8099 (exposed)

## Features

- **Device Management**: Commission, list, and remove Matter devices
- **Device Binding**: Create bindings between Matter devices
- **OTA Updates**: Trigger firmware updates for Matter devices
- **REST API**: Comprehensive API for integration with external applications
- **WebSocket Support**: Real-time updates for device status, logs, and analytics
- **Analytics**: Track device usage and events
- **Logging**: Detailed logging for troubleshooting
- **Hub Management**: Manage the Matter hub running on Home Assistant

## Installation

1. Add this repository to your Home Assistant instance:
   ```
   https://github.com/schnellenergy/ha-matter-addon
   ```
2. Install the "Matter Controller" add-on
3. Configure the add-on with your preferences
4. Start the add-on

## Configuration

The add-on can be configured through the Home Assistant UI. Available options:

| Option | Description | Default |
|--------|-------------|---------|
| `log_level` | The log level for the add-on | `info` |
| `log_level_sdk` | The log level for the Matter SDK | `error` |
| `token_lifetime_days` | Number of days before API tokens expire | `30` |
| `allow_external_commissioning` | Enable/disable external commissioning | `true` |
| `analytics_enabled` | Enable/disable analytics collection | `true` |
| `max_log_entries` | Maximum number of log entries to store | `1000` |
| `max_analytics_events` | Maximum number of analytics events to store | `1000` |
| `auto_register_with_ha` | Automatically register devices with Home Assistant | `true` |

## API Endpoints

The add-on exposes a REST API on port 8099 that can be used to interact with Matter devices:

### Authentication

- `POST /api/token`: Get an API token for authentication

### Device Management

- `POST /api/commission`: Commission a device using a setup code
- `GET /api/devices`: List all commissioned devices
- `DELETE /api/devices/{id}`: Remove a device

### Device Control

- `POST /api/binding`: Create a binding between devices
- `POST /api/ota/update`: Trigger an OTA update for a device

### Analytics and Logging

- `POST /api/analytics`: Get analytics data
- `POST /api/logs`: Get log entries
- `GET /api/hub`: Get information about the Matter hub

### WebSocket Endpoints

- `/ws/devices`: Real-time device updates
- `/ws/logs`: Real-time log updates
- `/ws/analytics`: Real-time analytics updates

## Usage Examples

### Commissioning a Device

```http
POST http://homeassistant.local:8099/api/commission
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "setup_code": "MT:ABCDEFG",
  "device_name": "Living Room Light"
}
```

### Listing Devices

```http
GET http://homeassistant.local:8099/api/devices
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### Creating a Binding

```http
POST http://homeassistant.local:8099/api/binding
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "source_device_id": "123456",
  "target_device_id": "789012",
  "cluster_id": 6
}
```

## Troubleshooting

If you encounter issues:

1. Check the add-on logs for error messages
2. Ensure that the Matter integration is installed in Home Assistant
3. Verify that your Home Assistant instance is accessible from your client device
4. Check that the port 8099 is open and accessible

### Common Issues

#### Matter Server Not Starting

If the Matter Server fails to start:

1. Check the logs for any error messages related to the Matter Server
2. Try setting `log_level_sdk` to `detail` for more verbose logging
3. Restart the add-on
4. If the issue persists, try uninstalling and reinstalling the add-on

#### Commissioning Failures

If device commissioning fails:

1. Make sure the device is in commissioning mode
2. Check that the setup code is correct
3. Ensure the device is within range of your Home Assistant server
4. Verify that Bluetooth is enabled on your Home Assistant server (if required by the device)
5. Try setting `log_level_sdk` to `detail` for more verbose logging during commissioning

## Support

For issues and feature requests, please open an issue on the GitHub repository:
https://github.com/schnellenergy/ha-matter-addon/issues

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
