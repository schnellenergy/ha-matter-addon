# Matter Controller Add-on for Home Assistant

This add-on provides a custom Matter controller that allows commissioning Matter devices from external applications and integrating them with Home Assistant.

## Features

- Commission Matter devices using setup codes or QR codes
- Manage commissioned devices
- Create bindings between devices
- Trigger OTA updates
- REST API and WebSocket interface
- Analytics and logging

## Installation

1. Add the repository to your Home Assistant instance.
2. Install the "Matter Controller" add-on.
3. Configure the add-on options.
4. Start the add-on.

## Configuration

```yaml
log_level: info
log_level_sdk: error
token_lifetime_days: 30
allow_external_commissioning: true
analytics_enabled: true
max_log_entries: 1000
max_analytics_events: 1000
auto_register_with_ha: true
```

### Option: `log_level`

The `log_level` option controls the level of log output by the add-on and can be changed to be more or less verbose, which might be useful when you are dealing with an unknown issue.

### Option: `log_level_sdk`

The `log_level_sdk` option controls the level of log output by the Matter SDK.

### Option: `token_lifetime_days`

The number of days that API tokens are valid for.

### Option: `allow_external_commissioning`

Whether to allow external apps to commission devices through this add-on.

### Option: `analytics_enabled`

Whether to collect analytics data.

### Option: `max_log_entries`

Maximum number of log entries to keep.

### Option: `max_analytics_events`

Maximum number of analytics events to keep.

### Option: `auto_register_with_ha`

Whether to automatically register commissioned devices with Home Assistant.

## API

The add-on provides a REST API and WebSocket interface for interacting with Matter devices.

### Authentication

To use the API, you need to obtain an access token:

```
POST /api/token
{
  "client_id": "your_client_id",
  "client_name": "Your Client Name"
}
```

### Commissioning

Commission a new Matter device:

```
POST /api/commission
{
  "setup_code": "MT:ABCDEFG",
  "device_name": "Living Room Light"
}
```

### Device Management

Get all commissioned devices:

```
GET /api/devices
```

Remove a device:

```
DELETE /api/devices/{device_id}
```

### Bindings

Create a binding between two devices:

```
POST /api/binding
{
  "source_device_id": "123",
  "target_device_id": "456",
  "cluster_id": 6
}
```

### OTA Updates

Trigger an OTA update for a device:

```
POST /api/ota/update
{
  "device_id": "123"
}
```

## Support

If you have any issues or questions, please open an issue on GitHub.

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
