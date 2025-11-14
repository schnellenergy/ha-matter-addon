import 'dart:developer';
import 'package:dio/dio.dart';
// import 'package:socket_io_client/socket_io_client.dart' as io;

/// Custom Data Storage Service for Flutter Integration
/// Provides easy access to the Custom Data Storage Home Assistant Add-on
class CustomDataStorageService {
  final Dio _dio = Dio();
  final String baseUrl;
  final String? apiKey;
  // Socket? _socket; // Uncomment when socket_io_client is added to pubspec.yaml

  // Callbacks for real-time updates
  Function(String category, String key, dynamic value)? onDataUpdated;
  Function(String category, String key)? onDataDeleted;
  Function()? onConnected;
  Function()? onDisconnected;

  CustomDataStorageService({
    required this.baseUrl, // e.g., 'http://192.168.1.100:8100'
    this.apiKey,
  }) {
    _setupDio();
  }

  void _setupDio() {
    _dio.options.baseUrl = baseUrl;
    _dio.options.connectTimeout = const Duration(seconds: 10);
    _dio.options.receiveTimeout = const Duration(seconds: 10);

    if (apiKey != null) {
      _dio.options.headers['X-API-Key'] = apiKey;
    }
  }

  /// Store data in the custom storage
  Future<bool> storeData({
    required String key,
    required dynamic value,
    String category = 'default',
  }) async {
    try {
      final response = await _dio.post(
        '/api/data',
        data: {'key': key, 'value': value, 'category': category},
      );

      log('✅ Data stored: $category.$key = $value');
      return response.data['success'] == true;
    } catch (e) {
      log('❌ Error storing data: $e');
      return false;
    }
  }

  /// Get specific data from storage
  Future<T?> getData<T>({
    required String key,
    String category = 'default',
  }) async {
    try {
      final response = await _dio.get('/api/data/$category/$key');

      if (response.data['success'] == true) {
        return response.data['value'] as T?;
      }
      return null;
    } catch (e) {
      log('❌ Error getting data: $e');
      return null;
    }
  }

  /// Get all data in a category
  Future<Map<String, dynamic>?> getCategoryData(String category) async {
    try {
      final response = await _dio.get('/api/data/$category');

      if (response.data['success'] == true) {
        return Map<String, dynamic>.from(response.data['data']);
      }
      return null;
    } catch (e) {
      log('❌ Error getting category data: $e');
      return null;
    }
  }

  /// Get all data from storage
  Future<Map<String, dynamic>?> getAllData() async {
    try {
      final response = await _dio.get('/api/data');

      if (response.data['success'] == true) {
        return Map<String, dynamic>.from(response.data['data']);
      }
      return null;
    } catch (e) {
      log('❌ Error getting all data: $e');
      return null;
    }
  }

  /// Delete specific data
  Future<bool> deleteData({
    required String key,
    String category = 'default',
  }) async {
    try {
      final response = await _dio.delete('/api/data/$category/$key');

      log('🗑️ Data deleted: $category.$key');
      return response.data['success'] == true;
    } catch (e) {
      log('❌ Error deleting data: $e');
      return false;
    }
  }

  /// Get storage metadata
  Future<Map<String, dynamic>?> getMetadata() async {
    try {
      final response = await _dio.get('/api/metadata');
      return Map<String, dynamic>.from(response.data);
    } catch (e) {
      log('❌ Error getting metadata: $e');
      return null;
    }
  }

  /// Connect to WebSocket for real-time updates
  /// To enable WebSocket functionality:
  /// 1. Add to pubspec.yaml: socket_io_client: ^2.0.3+1
  /// 2. Uncomment the WebSocket code below
  /// 3. Uncomment the _socket field declaration
  void connectWebSocket() {
    log(
      'WebSocket functionality disabled - add socket_io_client dependency to enable',
    );

    /* Uncomment when socket_io_client is added to pubspec.yaml:
    try {
      _socket = io.io(baseUrl, <String, dynamic>{
        'transports': ['websocket'],
        'autoConnect': true,
      });

      _socket!.on('connect', (_) {
        log('🔌 Connected to Custom Data Storage WebSocket');
        onConnected?.call();
      });

      _socket!.on('disconnect', (_) {
        log('🔌 Disconnected from Custom Data Storage WebSocket');
        onDisconnected?.call();
      });

      _socket!.on('data_updated', (data) {
        log('📊 Data updated via WebSocket: $data');

        final action = data['action'];
        final category = data['category'];
        final key = data['key'];

        if (action == 'set') {
          final value = data['value'];
          onDataUpdated?.call(category, key, value);
        } else if (action == 'delete') {
          onDataDeleted?.call(category, key);
        }
      });

      _socket!.on('error', (error) {
        log('❌ WebSocket error: $error');
      });
    } catch (e) {
      log('❌ Error connecting to WebSocket: $e');
    }
    */
  }

  /// Disconnect from WebSocket
  void disconnectWebSocket() {
    log(
      'WebSocket functionality disabled - add socket_io_client dependency to enable',
    );
    /* Uncomment when socket_io_client is added:
    _socket?.disconnect();
    _socket = null;
    log('🔌 WebSocket disconnected');
    */
  }

  /// Request data via WebSocket
  void requestDataViaWebSocket({String? category, String? key}) {
    log(
      'WebSocket functionality disabled - add socket_io_client dependency to enable',
    );
    /* Uncomment when socket_io_client is added:
    if (_socket?.connected == true) {
      _socket!.emit('get_data', {
        if (category != null) 'category': category,
        if (key != null) 'key': key,
      });
    }
    */
  }

  /// Check if WebSocket is connected
  bool get isWebSocketConnected =>
      false; // Change to: _socket?.connected == true when enabled

  /// Dispose resources
  void dispose() {
    disconnectWebSocket();
    _dio.close();
  }
}

/// Example usage in a Flutter app
class CustomDataExample {
  late CustomDataStorageService _dataService;

  void initializeService() {
    _dataService = CustomDataStorageService(
      baseUrl: 'http://192.168.1.100:8100', // Replace with your HA IP
      apiKey: 'your-optional-api-key',
    );

    // Set up real-time update callbacks
    _dataService.onDataUpdated = (category, key, value) {
      log('Data updated: $category.$key = $value');
      // Update your app UI here
    };

    _dataService.onDataDeleted = (category, key) {
      log('Data deleted: $category.$key');
      // Update your app UI here
    };

    _dataService.onConnected = () {
      log('WebSocket connected - real-time updates enabled');
    };

    // Connect to WebSocket for real-time updates
    _dataService.connectWebSocket();
  }

  /// Example: Store user preferences
  Future<void> storeUserPreferences() async {
    await _dataService.storeData(
      key: 'theme',
      value: 'dark',
      category: 'user_preferences',
    );

    await _dataService.storeData(
      key: 'language',
      value: 'en',
      category: 'user_preferences',
    );

    await _dataService.storeData(
      key: 'notifications_enabled',
      value: true,
      category: 'user_preferences',
    );
  }

  /// Example: Get user preferences
  Future<Map<String, dynamic>> getUserPreferences() async {
    final theme = await _dataService.getData<String>(
      key: 'theme',
      category: 'user_preferences',
    );

    final language = await _dataService.getData<String>(
      key: 'language',
      category: 'user_preferences',
    );

    final notificationsEnabled = await _dataService.getData<bool>(
      key: 'notifications_enabled',
      category: 'user_preferences',
    );

    return {
      'theme': theme ?? 'light',
      'language': language ?? 'en',
      'notifications_enabled': notificationsEnabled ?? true,
    };
  }

  /// Example: Store device custom properties
  Future<void> storeDeviceProperties() async {
    await _dataService.storeData(
      key: 'fan.living_room',
      value: {
        'custom_name': 'Main Living Room Fan',
        'room_icon': '🌀',
        'favorite': true,
        'custom_speeds': ['Low', 'Medium', 'High', 'Turbo'],
      },
      category: 'device_properties',
    );

    await _dataService.storeData(
      key: 'light.kitchen',
      value: {
        'custom_name': 'Kitchen Lights',
        'room_icon': '💡',
        'favorite': false,
        'color_presets': ['Warm', 'Cool', 'Reading', 'Party'],
      },
      category: 'device_properties',
    );
  }

  /// Example: Get device properties
  Future<Map<String, dynamic>?> getDeviceProperties(String entityId) async {
    return await _dataService.getData<Map<String, dynamic>>(
      key: entityId,
      category: 'device_properties',
    );
  }

  /// Example: Store app configuration
  Future<void> storeAppConfig() async {
    await _dataService.storeData(
      key: 'auto_refresh_interval',
      value: 30,
      category: 'app_config',
    );

    await _dataService.storeData(
      key: 'default_room',
      value: 'living_room',
      category: 'app_config',
    );

    await _dataService.storeData(
      key: 'enable_analytics',
      value: true,
      category: 'app_config',
    );
  }

  /// Example: Get storage statistics
  Future<void> getStorageInfo() async {
    final metadata = await _dataService.getMetadata();
    if (metadata != null) {
      log('Storage size: ${metadata['storage_size_mb']} MB');
      log('Total categories: ${metadata['categories'].length}');
      log('Total values: ${metadata['total_values']}');
      log('Last updated: ${metadata['last_updated']}');
    }
  }

  /// Clean up resources
  void dispose() {
    _dataService.dispose();
  }
}

/// Widget example for using the service
/*
class CustomDataWidget extends StatefulWidget {
  @override
  _CustomDataWidgetState createState() => _CustomDataWidgetState();
}

class _CustomDataWidgetState extends State<CustomDataWidget> {
  final CustomDataExample _example = CustomDataExample();
  String _currentTheme = 'light';

  @override
  void initState() {
    super.initState();
    _example.initializeService();
    _loadUserPreferences();
  }

  Future<void> _loadUserPreferences() async {
    final prefs = await _example.getUserPreferences();
    setState(() {
      _currentTheme = prefs['theme'] ?? 'light';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Custom Data Storage Example')),
      body: Column(
        children: [
          Text('Current Theme: $_currentTheme'),
          ElevatedButton(
            onPressed: () async {
              final newTheme = _currentTheme == 'light' ? 'dark' : 'light';
              await _example._dataService.storeData(
                key: 'theme',
                value: newTheme,
                category: 'user_preferences',
              );
              setState(() {
                _currentTheme = newTheme;
              });
            },
            child: Text('Toggle Theme'),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _example.dispose();
    super.dispose();
  }
}
*/
