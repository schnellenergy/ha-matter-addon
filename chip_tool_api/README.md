# 🔧 CHIP Tool API Add-on

A Home Assistant add-on that exposes the Matter chip-tool via HTTP API for easy device commissioning, control, and binding operations.

## 🎯 Features

- **HTTP API** for Matter chip-tool operations
- **Device Commissioning** pair Matter devices via API
- **Device Control** toggle and control Matter devices
- **Binding Operations** create bindings between Matter devices
- **Storage Management** clear chip-tool storage
- **Real-time Logs** view chip-tool stdout/stderr in real-time
- **Multi-architecture Support** works on all Home Assistant platforms

## 📚 API Endpoints

### Device Commissioning
```bash
POST http://homeassistant.local:6000/pair
{
  "node_id": "1",
  "setup_code": "20202021",
  "discriminator": "3840"
}
```

### Device Control (Toggle)
```bash
POST http://homeassistant.local:6000/toggle
{
  "node_id": "1",
  "endpoint": "1"
}
```

### Create Binding
```bash
POST http://homeassistant.local:6000/bind
{
  "source_node": "1",
  "source_endpoint": "1",
  "destination_node": "2",
  "destination_endpoint": "1",
  "cluster_id": "6"
}
```

### Clear Storage
```bash
POST http://homeassistant.local:6000/command
{
  "storage": "clear-all"
}
```

## 🚀 Quick Start

1. Install the add-on from the Add-on Store
2. Start the add-on
3. The API will be available at `http://homeassistant.local:6000`

## 📖 Configuration

No configuration required! The add-on works out of the box.

## 🔍 Troubleshooting

### API not responding
- Check if the add-on is running
- Verify port 6000 is not blocked
- Check add-on logs for errors

### Commissioning fails
- Verify the setup code and discriminator are correct
- Ensure the Matter device is in pairing mode
- Check that the node_id is not already in use

### Binding fails
- Ensure both devices are commissioned
- Verify the cluster_id is supported by both devices
- Check that endpoints are correct

## 🛠️ Advanced Usage

### Using with Flutter App
```dart
import 'package:dio/dio.dart';

final dio = Dio();
final response = await dio.post(
  'http://192.168.6.166:6000/pair',
  data: {
    'node_id': '1',
    'setup_code': '20202021',
    'discriminator': '3840',
  },
);
```

### Using with Home Assistant Automation
```yaml
automation:
  - alias: "Commission Matter Device"
    trigger:
      - platform: state
        entity_id: input_boolean.commission_device
        to: 'on'
    action:
      - service: rest_command.commission_matter_device
        data:
          node_id: "{{ states('input_number.node_id') }}"
          setup_code: "{{ states('input_text.setup_code') }}"
```

## 📝 Notes

- The chip-tool storage is persistent across restarts
- Use the `/command` endpoint with `storage: clear-all` to reset
- All operations return JSON with `success`, `message`, and `stdout` fields
- Check the add-on logs for detailed chip-tool output

## 🔗 Related Add-ons

- **Binding Feature** - Create and manage Matter device bindings
- **Custom Data Storage** - Store binding configurations
- **SMASH Hub BLE WiFi Onboarding** - WiFi provisioning for Matter devices

## 📄 License

This add-on is part of the Schnell Home Automation project.

## 🤝 Support

For issues and questions, please check the add-on logs first, then open an issue on GitHub.
