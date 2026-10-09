# Matter Device Binding System

A comprehensive Matter device binding implementation for the Schnell Home Automation Flutter app. This system enables commissioning Matter devices and creating hard bindings between them (e.g., switch to light, sensor to actuator) using chip-tool REST API integration.

## Overview

The Matter binding system consists of:

- **Flutter UI**: Three-tab interface for device management, binding creation, and binding list
- **REST API Integration**: Communicates with chip-tool Docker container via HTTP endpoints
- **Local Storage**: JSON-based storage for device and binding data
- **Real-time Updates**: Automatic refresh and status updates

## Key Features

- **Device Commissioning**: Pair Matter devices using passcode with auto or manual node ID assignment
- **Hard Binding Creation**: Create direct bindings between Matter devices (switch controls light directly)
- **Device Management**: List, view, and manage commissioned Matter devices
- **Binding Management**: View, track, and manage active device bindings
- **Endpoint Configuration**: Support for multiple endpoints per device (default: endpoint 1)
- **Local Data Persistence**: Store device and binding data locally using JSON storage

## Architecture

### System Components

1. **Flutter UI Layer** (`new_binding_screen.dart`)

   - Three-tab interface: Devices, Create Binding, Bindings
   - Device commissioning dialog with passcode input
   - Binding creation form with device selection
   - Real-time status updates and error handling

2. **API Service Layer** (`new_binding_api_service.dart`)

   - REST API communication with chip-tool container
   - Device pairing and binding operations
   - Response parsing and error handling
   - Local storage integration

3. **Storage Layer** (`binding_storage_service.dart`)

   - JSON-based local storage for devices and bindings
   - Node ID management and auto-increment
   - Data persistence and retrieval

4. **Backend API** (Docker Container)
   - chip-tool REST API endpoints
   - Matter device commissioning
   - Binding creation and management

## API Configuration

### API Endpoints

The system uses the following REST API endpoints:

```dart
// API Configuration (lib/config/api_config.dart)
class ApiConfig {
  static const String chipToolBaseUrl = 'http://192.168.6.166:6000';
  static String get pairUrl => '$chipToolBaseUrl/pair';
  static String get bindUrl => '$chipToolBaseUrl/bind';
  static String get toggleUrl => '$chipToolBaseUrl/toggle';
  static String get commandUrl => '$chipToolBaseUrl/command';
}
```

### Supported Operations

1. **Device Pairing** (`POST /pair`)

   - Commission Matter devices using passcode
   - Auto or manual node ID assignment
   - Device type specification

2. **Device Binding** (`POST /bind`)

   - Create hard bindings between devices
   - Source and target device specification
   - Endpoint configuration

3. **Device Testing** (`POST /toggle`)

   - Test device functionality
   - Verify binding operations

4. **Storage Management** (`POST /command`)
   - Clear chip-tool storage
   - Reset device configurations

## Implementation Details

### Device Pairing Process

The device pairing process follows these steps:

1. **User Input**: User enters device name, type, and passcode
2. **Node ID Assignment**: System auto-generates or accepts manual node ID
3. **API Call**: Send pairing request to chip-tool container
4. **Device Storage**: Store device information locally
5. **UI Update**: Refresh device list and show success/error message

### Binding Creation Process

The binding creation process involves:

1. **Device Selection**: User selects source and target devices from dropdown
2. **Endpoint Configuration**: Set source and target endpoints (default: 1)
3. **API Call**: Send binding request to chip-tool container
4. **Local Storage**: Store binding information locally
5. **UI Update**: Refresh binding list and show confirmation

### Data Models

#### PairedDevice Model

```dart
class PairedDevice {
  final String id;
  final String name;
  final String deviceType;
  final int nodeId;
  final DateTime pairedAt;

  // Constructor and methods...
}
```

#### DeviceBinding Model

```dart
class DeviceBinding {
  final String id;
  final int sourceNodeId;
  final int sourceEndpoint;
  final int targetNodeId;
  final int targetEndpoint;
  final String sourceName;
  final String targetName;
  final DateTime createdAt;

  // Constructor and methods...
}
```

## Core Implementation

### 1. API Service Layer (`new_binding_api_service.dart`)

```dart
class NewBindingApiService {
  static String get pairUrl => ApiConfig.pairUrl;
  static String get bindUrl => ApiConfig.bindUrl;

  final BindingStorageService _storageService = BindingStorageService();

  // Pair a device using passcode and auto-generated node ID
  Future<PairedDevice?> pairDevice({
    required String deviceName,
    required String deviceType,
    required String passcode,
  }) async {
    try {
      // Get next available node ID
      final nodeId = await _storageService.getNextNodeId();

      return await pairDeviceWithNodeId(
        deviceName: deviceName,
        deviceType: deviceType,
        passcode: passcode,
        nodeId: nodeId,
      );
    } catch (e) {
      log('Error pairing device: $e');
      return null;
    }
  }

  // Pair a device using passcode and manual node ID
  Future<PairedDevice?> pairDeviceWithNodeId({
    required String deviceName,
    required String deviceType,
    required String passcode,
    required int nodeId,
  }) async {
    try {
      log('Pairing device: $deviceName with node ID: $nodeId');

      var headers = ApiConfig.headers;
      var data = json.encode({'node_id': nodeId, 'passcode': passcode});

      var dio = ApiConfig.getDio();
      var response = await dio.request(
        pairUrl,
        options: Options(method: 'POST', headers: headers),
        data: data,
      );

      if (response.statusCode == 200) {
        final chipToolResponse = ChipToolResponse.fromJson(response.data);

        if (chipToolResponse.success) {
          // Create device object
          final device = PairedDevice(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            name: deviceName,
            deviceType: deviceType,
            nodeId: nodeId,
            pairedAt: DateTime.now(),
          );

          // Save to local storage
          await _storageService.addPairedDevice(device);

          log('Device paired successfully: $deviceName (Node ID: $nodeId)');
          return device;
        }
      }

      return null;
    } catch (e) {
      log('Error pairing device: $e');
      return null;
    }
  }

  // Create binding between two devices
  Future<DeviceBinding?> createBinding({
    required int sourceNodeId,
    required int sourceEndpoint,
    required int targetNodeId,
    required int targetEndpoint,
  }) async {
    try {
      log('Creating binding: Source($sourceNodeId:$sourceEndpoint) -> Target($targetNodeId:$targetEndpoint)');

      var headers = ApiConfig.headers;
      var data = json.encode({
        'switch_node': sourceNodeId,
        'switch_endpoint': sourceEndpoint,
        'light_node': targetNodeId,
        'light_endpoint': targetEndpoint,
      });

      var dio = ApiConfig.getDio();
      var response = await dio.request(
        bindUrl,
        options: Options(method: 'POST', headers: headers),
        data: data,
      );

      if (response.statusCode == 200) {
        final chipToolResponse = ChipToolResponse.fromJson(response.data);

        if (chipToolResponse.success) {
          // Get device names for the binding
          final sourceDevice = await _storageService.getDeviceByNodeId(sourceNodeId);
          final targetDevice = await _storageService.getDeviceByNodeId(targetNodeId);

          // Create binding object
          final binding = DeviceBinding(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            sourceNodeId: sourceNodeId,
            sourceEndpoint: sourceEndpoint,
            targetNodeId: targetNodeId,
            targetEndpoint: targetEndpoint,
            sourceName: sourceDevice?.name ?? 'Unknown Device',
            targetName: targetDevice?.name ?? 'Unknown Device',
            createdAt: DateTime.now(),
          );

          // Save to local storage
          await _storageService.addDeviceBinding(binding);

          log('Binding created successfully: ${binding.sourceName} -> ${binding.targetName}');
          return binding;
        }
      }

      return null;
    } catch (e) {
      log('Error creating binding: $e');
      return null;
    }
  }
}
```

### 2. Flutter UI Implementation (`new_binding_screen.dart`)

```dart
class NewBindingScreen extends StatefulWidget {
  const NewBindingScreen({super.key});

  @override
  State<NewBindingScreen> createState() => _NewBindingScreenState();
}

class _NewBindingScreenState extends State<NewBindingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final NewBindingApiService _apiService = NewBindingApiService();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Matter Device Binding'),
        backgroundColor: Colors.blue,
        foregroundColor: Colors.white,
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white70,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(icon: Icon(Icons.devices), text: 'Devices'),
            Tab(icon: Icon(Icons.link), text: 'Create Binding'),
            Tab(icon: Icon(Icons.list), text: 'Bindings'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          DevicesTab(apiService: _apiService),
          CreateBindingTab(apiService: _apiService),
          BindingsTab(apiService: _apiService),
        ],
      ),
    );
  }
}

// Device Pairing Dialog
Future<void> _pairDevice() async {
  setState(() => _isPairing = true);

  try {
    final device = await widget.apiService.pairDeviceWithNodeId(
      deviceName: _nameController.text,
      deviceType: _selectedDeviceType,
      passcode: _passcodeController.text,
      nodeId: nodeId,
    );

    if (mounted) {
      if (device != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Device "${device.name}" paired successfully with Node ID ${device.nodeId}',
            ),
            backgroundColor: Colors.green,
          ),
        );
        Navigator.pop(context, true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Failed to pair device. Please check the passcode and try again.',
            ),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  } finally {
    if (mounted) setState(() => _isPairing = false);
  }
}

// Binding Creation
Future<void> _createBinding() async {
  if (_selectedSourceDevice == null || _selectedTargetDevice == null) return;

  setState(() => _isCreating = true);

  try {
    final binding = await widget.apiService.createBinding(
      sourceNodeId: _selectedSourceDevice!.nodeId,
      sourceEndpoint: _sourceEndpoint,
      targetNodeId: _selectedTargetDevice!.nodeId,
      targetEndpoint: _targetEndpoint,
    );

    if (mounted) {
      if (binding != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Binding created successfully: ${binding.sourceName} → ${binding.targetName}',
            ),
            backgroundColor: Colors.green,
          ),
        );

        // Clear form
        setState(() {
          _selectedSourceDevice = null;
          _selectedTargetDevice = null;
          _sourceEndpoint = 1;
          _targetEndpoint = 1;
        });
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Failed to create binding. Please check the configuration.',
            ),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  } finally {
    if (mounted) setState(() => _isCreating = false);
  }
}
```

### 3. REST API Examples

#### Device Pairing API Call

```bash
# Pair a Matter device using passcode
curl -X POST "http://192.168.6.166:6000/pair" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": 3,
    "passcode": "20202021"
  }'

# Expected Response
{
  "success": true,
  "message": "Device commissioned successfully",
  "node_id": 3,
  "stdout": "Device commissioning completed",
  "stderr": ""
}
```

#### Device Binding API Call

```bash
# Create binding between switch (node 1) and light (node 2)
curl -X POST "http://192.168.6.166:6000/bind" \
  -H "Content-Type: application/json" \
  -d '{
    "switch_node": 1,
    "switch_endpoint": 1,
    "light_node": 2,
    "light_endpoint": 1
  }'

# Expected Response
{
  "success": true,
  "message": "Binding created successfully",
  "binding_details": {
    "source": "Node 1, Endpoint 1",
    "target": "Node 2, Endpoint 1"
  },
  "stdout": "Binding operation completed",
  "stderr": ""
}
```

#### Device Testing API Call

```bash
# Toggle device for testing
curl -X POST "http://192.168.6.166:6000/toggle" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": 2
  }'

# Expected Response
{
  "success": true,
  "message": "Device toggled successfully",
  "node_id": 2,
  "stdout": "Toggle command executed",
  "stderr": ""
}
```

#### Storage Management API Call

```bash
# Clear chip-tool storage
curl -X POST "http://192.168.6.166:6000/command" \
  -H "Content-Type: application/json" \
  -d '{
    "args": ["clear-all"]
  }'

# Expected Response
{
  "success": true,
  "message": "Storage cleared successfully",
  "stdout": "All storage cleared",
  "stderr": ""
}
```

## Local Storage Structure

### JSON Storage Files

The system uses JSON files for local data persistence:

```
/data/
├── paired_devices.json      # List of commissioned devices
├── device_bindings.json     # List of active bindings
└── app_settings.json        # App configuration and next node ID
```

### Storage Service Implementation

```dart
class BindingStorageService {
  // Get next available node ID
  Future<int> getNextNodeId() async {
    final settings = await _loadSettings();
    final nextNodeId = settings['next_node_id'] ?? 1;

    // Update next node ID
    settings['next_node_id'] = nextNodeId + 1;
    await _saveSettings(settings);

    return nextNodeId;
  }

  // Add paired device to storage
  Future<void> addPairedDevice(PairedDevice device) async {
    final devices = await getAllPairedDevices();
    devices.add(device);
    await _savePairedDevices(devices);
  }

  // Add device binding to storage
  Future<void> addDeviceBinding(DeviceBinding binding) async {
    final bindings = await getAllDeviceBindings();
    bindings.add(binding);
    await _saveDeviceBindings(bindings);
  }

  // Get device by node ID
  Future<PairedDevice?> getDeviceByNodeId(int nodeId) async {
    final devices = await getAllPairedDevices();
    try {
      return devices.firstWhere((device) => device.nodeId == nodeId);
    } catch (e) {
      return null;
    }
  }
}
```

## User Interface

### Three-Tab Interface

#### 1. Devices Tab

- **Device List**: Shows all commissioned Matter devices
- **Add Device Button**: Opens pairing dialog
- **Device Cards**: Display device name, type, node ID, and pairing date
- **Delete Option**: Remove devices from local storage

#### 2. Create Binding Tab

- **Source Device Dropdown**: Select controlling device (switch, sensor)
- **Target Device Dropdown**: Select controlled device (light, fan)
- **Endpoint Configuration**: Set source and target endpoints (default: 1)
- **Create Binding Button**: Execute binding creation
- **Form Validation**: Ensure different devices are selected

#### 3. Bindings Tab

- **Binding List**: Shows all active device bindings
- **Binding Cards**: Display source → target relationship
- **Creation Date**: When binding was created
- **Delete Option**: Remove bindings from local storage

### Device Pairing Dialog

```dart
// Pairing dialog fields
- Device Name (Text Input)
- Device Type (Dropdown: Switch, Light, Fan, Sensor, Outlet, Dimmer)
- Passcode (Text Input with validation)
- Node ID (Auto-generated or manual input)
- Pair Device Button (with loading indicator)
```

### Error Handling

- **Network Errors**: Show connection failure messages
- **API Errors**: Display chip-tool error responses
- **Validation Errors**: Highlight invalid form fields
- **Success Messages**: Confirm successful operations

## Troubleshooting

### Common Issues

1. **Device Pairing Fails**

   - **Check Passcode**: Ensure the Matter device passcode is correct
   - **Device Mode**: Verify device is in pairing/commissioning mode
   - **Network**: Ensure device and Home Assistant are on same network
   - **Node ID**: Try different node ID if current one is in use

2. **Binding Creation Fails**

   - **Device Status**: Verify both devices are successfully paired
   - **Endpoints**: Check that endpoints 1 are supported by devices
   - **Device Types**: Ensure source device can control target device
   - **API Response**: Check chip-tool logs for detailed error messages

3. **API Connection Issues**

   - **Container Status**: Verify chip-tool Docker container is running
   - **Port Access**: Ensure port 6000 is accessible
   - **Network Configuration**: Check IP address in ApiConfig
   - **Firewall**: Verify no firewall blocking the connection

4. **UI Issues**
   - **Data Loading**: Check if local storage files are accessible
   - **State Updates**: Restart app if UI doesn't reflect changes
   - **Form Validation**: Ensure all required fields are filled

### Debug Steps

1. **Check API Connectivity**

   ```bash
   curl -X GET "http://192.168.6.166:6000"
   ```

2. **Test Device Pairing**

   ```bash
   curl -X POST "http://192.168.6.166:6000/pair" \
     -H "Content-Type: application/json" \
     -d '{"node_id": 99, "passcode": "20202021"}'
   ```

3. **Clear Storage if Needed**
   ```bash
   curl -X POST "http://192.168.6.166:6000/command" \
     -H "Content-Type: application/json" \
     -d '{"args": ["clear-all"]}'
   ```

### Logging

- **Flutter Logs**: Check console output for API call details
- **Container Logs**: Monitor chip-tool container logs for errors
- **Network Logs**: Use network inspector to debug API requests

## Key Features Summary

### ✅ Implemented Features

- **Device Commissioning**: Pair Matter devices using passcode
- **Hard Binding**: Create direct device-to-device bindings
- **Three-Tab UI**: Devices, Create Binding, Bindings management
- **Local Storage**: JSON-based persistence for devices and bindings
- **Auto Node ID**: Automatic node ID assignment with manual override
- **Error Handling**: Comprehensive error messages and validation
- **Real-time Updates**: Immediate UI updates after operations

### 🔧 Technical Details

- **API Integration**: RESTful communication with chip-tool container
- **Data Models**: Structured PairedDevice and DeviceBinding classes
- **Storage Service**: Centralized data persistence management
- **UI Components**: Material Design with blue theme
- **Form Validation**: Input validation and user feedback
- **Loading States**: Progress indicators during operations

### 📱 User Experience

- **Intuitive Interface**: Clear three-tab navigation
- **Quick Pairing**: Simple device commissioning process
- **Easy Binding**: Dropdown device selection for binding creation
- **Visual Feedback**: Success/error messages and loading indicators
- **Data Management**: View and delete devices and bindings

This Matter device binding system provides a complete solution for commissioning Matter devices and creating hard bindings between them, with a user-friendly Flutter interface and robust REST API integration.
