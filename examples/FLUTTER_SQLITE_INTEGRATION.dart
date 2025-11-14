import 'dart:developer';
import 'package:dio/dio.dart';
// import 'package:socket_io_client/socket_io_client.dart' as io;

/// SQLite Custom Data Storage Service for Flutter
/// Professional database integration for large-scale data management
class SQLiteDataStorageService {
  final Dio _dio = Dio();
  final String baseUrl;
  final String? apiKey;
  // Socket? _socket; // Uncomment when socket_io_client is added to pubspec.yaml

  // Callbacks for real-time updates
  Function(String category, String key, dynamic value)? onDataUpdated;
  Function(String category, String key)? onDataDeleted;
  Function()? onConnected;
  Function()? onDisconnected;

  SQLiteDataStorageService({
    required this.baseUrl, // e.g., 'http://192.168.1.100:8100'
    this.apiKey,
  }) {
    _setupDio();
  }

  void _setupDio() {
    _dio.options.baseUrl = baseUrl;
    _dio.options.connectTimeout = const Duration(seconds: 15);
    _dio.options.receiveTimeout = const Duration(seconds: 15);

    if (apiKey != null) {
      _dio.options.headers['X-API-Key'] = apiKey;
    }
  }

  /// Store data in SQLite database
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

      log('✅ SQLite: Data stored: $category.$key = $value');
      return response.data['success'] == true;
    } catch (e) {
      log('❌ SQLite: Error storing data: $e');
      return false;
    }
  }

  /// Get specific data from SQLite database
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
      log('❌ SQLite: Error getting data: $e');
      return null;
    }
  }

  /// Get all data in a category from SQLite
  Future<Map<String, dynamic>?> getCategoryData(String category) async {
    try {
      final response = await _dio.get('/api/data/$category');

      if (response.data['success'] == true) {
        return Map<String, dynamic>.from(response.data['data']);
      }
      return null;
    } catch (e) {
      log('❌ SQLite: Error getting category data: $e');
      return null;
    }
  }

  /// Get all data from SQLite database
  Future<Map<String, dynamic>?> getAllData() async {
    try {
      final response = await _dio.get('/api/data');

      if (response.data['success'] == true) {
        return Map<String, dynamic>.from(response.data['data']);
      }
      return null;
    } catch (e) {
      log('❌ SQLite: Error getting all data: $e');
      return null;
    }
  }

  /// Search data in SQLite database (powerful feature)
  Future<List<Map<String, dynamic>>> searchData({
    required String searchTerm,
    String? category,
  }) async {
    try {
      final queryParams = {'q': searchTerm};
      if (category != null) {
        queryParams['category'] = category;
      }

      final response = await _dio.get(
        '/api/search',
        queryParameters: queryParams,
      );

      if (response.data['success'] == true) {
        return List<Map<String, dynamic>>.from(response.data['results']);
      }
      return [];
    } catch (e) {
      log('❌ SQLite: Error searching data: $e');
      return [];
    }
  }

  /// Get list of all categories
  Future<List<String>> getCategories() async {
    try {
      final response = await _dio.get('/api/categories');

      if (response.data['success'] == true) {
        return List<String>.from(response.data['categories']);
      }
      return [];
    } catch (e) {
      log('❌ SQLite: Error getting categories: $e');
      return [];
    }
  }

  /// Delete specific data from SQLite
  Future<bool> deleteData({
    required String key,
    String category = 'default',
  }) async {
    try {
      final response = await _dio.delete('/api/data/$category/$key');

      log('🗑️ SQLite: Data deleted: $category.$key');
      return response.data['success'] == true;
    } catch (e) {
      log('❌ SQLite: Error deleting data: $e');
      return false;
    }
  }

  /// Get SQLite database metadata and statistics
  Future<Map<String, dynamic>?> getDatabaseMetadata() async {
    try {
      final response = await _dio.get('/api/metadata');
      return Map<String, dynamic>.from(response.data);
    } catch (e) {
      log('❌ SQLite: Error getting metadata: $e');
      return null;
    }
  }

  /// Optimize SQLite database performance
  Future<bool> optimizeDatabase() async {
    try {
      final response = await _dio.post('/api/optimize');
      return response.data['success'] == true;
    } catch (e) {
      log('❌ SQLite: Error optimizing database: $e');
      return false;
    }
  }

  /// Create SQLite database backup
  Future<String?> backupDatabase() async {
    try {
      final response = await _dio.post('/api/backup');
      if (response.data['success'] == true) {
        return response.data['backup_path'];
      }
      return null;
    } catch (e) {
      log('❌ SQLite: Error creating backup: $e');
      return null;
    }
  }

  /// Connect to WebSocket for real-time SQLite updates
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
        log('🔌 SQLite WebSocket: Connected');
        onConnected?.call();
      });

      _socket!.on('connected', (data) {
        log('🔌 SQLite WebSocket: Welcome - ${data['storage_type']}');
      });

      _socket!.on('disconnect', (_) {
        log('🔌 SQLite WebSocket: Disconnected');
        onDisconnected?.call();
      });

      _socket!.on('data_updated', (data) {
        log('📊 SQLite WebSocket: Data updated - $data');

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
        log('❌ SQLite WebSocket: Error - $error');
      });
    } catch (e) {
      log('❌ SQLite WebSocket: Connection error - $e');
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
    log('🔌 SQLite WebSocket: Disconnected');
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

/// Example usage for large-scale home automation data
class HomeAutomationDataManager {
  late SQLiteDataStorageService _dataService;

  void initialize() {
    _dataService = SQLiteDataStorageService(
      baseUrl: 'http://192.168.1.100:8100', // Your Home Assistant IP
      apiKey: 'your-optional-api-key',
    );

    // Set up real-time update callbacks
    _dataService.onDataUpdated = (category, key, value) {
      log('Real-time update: $category.$key = $value');
      _handleDataUpdate(category, key, value);
    };

    _dataService.onDataDeleted = (category, key) {
      log('Real-time deletion: $category.$key');
      _handleDataDeletion(category, key);
    };

    // Connect for real-time updates
    _dataService.connectWebSocket();
  }

  /// Store device properties (supports thousands of devices)
  Future<void> storeDeviceProperties() async {
    // Store complex device data
    await _dataService.storeData(
      key: 'fan.living_room',
      value: {
        'name': 'Main Living Room Fan',
        'icon': '🌀',
        'room': 'Living Room',
        'favorite': true,
        'custom_speeds': ['Low', 'Medium', 'High', 'Turbo'],
        'last_used': DateTime.now().toIso8601String(),
        'usage_count': 156,
        'energy_rating': 'A++',
        'manufacturer': 'Smart Home Co',
        'model': 'SH-FAN-2024',
        'installation_date': '2024-01-15',
        'warranty_expires': '2027-01-15',
      },
      category: 'devices',
    );

    // Store thousands of devices efficiently
    for (int i = 1; i <= 1000; i++) {
      await _dataService.storeData(
        key: 'device_$i',
        value: {
          'name': 'Device $i',
          'type': i % 2 == 0 ? 'light' : 'sensor',
          'room': 'Room ${(i % 10) + 1}',
          'online': i % 3 != 0,
          'last_seen': DateTime.now().toIso8601String(),
        },
        category: 'devices',
      );
    }
  }

  /// Store analytics data (supports millions of records)
  Future<void> storeAnalyticsData() async {
    // Store app usage analytics
    await _dataService.storeData(
      key: 'session_${DateTime.now().millisecondsSinceEpoch}',
      value: {
        'user_id': 'user_123',
        'session_start': DateTime.now().toIso8601String(),
        'app_version': '2.1.0',
        'device_model': 'Samsung SM E135F',
        'actions_performed': 25,
        'screens_visited': ['home', 'devices', 'settings', 'analytics'],
        'performance_metrics': {
          'avg_response_time': 150,
          'errors_encountered': 0,
          'network_requests': 45,
        },
      },
      category: 'analytics',
    );
  }

  /// Search functionality (powerful SQLite feature)
  Future<void> searchDevices(String searchTerm) async {
    final results = await _dataService.searchData(
      searchTerm: searchTerm,
      category: 'devices',
    );

    log('Found ${results.length} devices matching "$searchTerm":');
    for (final result in results) {
      log('- ${result['key']}: ${result['value']['name']}');
    }
  }

  /// Get database statistics
  Future<void> getDatabaseStats() async {
    final metadata = await _dataService.getDatabaseMetadata();
    if (metadata != null) {
      log('📊 SQLite Database Statistics:');
      log('   Total Records: ${metadata['total_values']}');
      log('   Categories: ${metadata['total_categories']}');
      log('   Database Size: ${metadata['database_size_mb']} MB');
      log('   Total Operations: ${metadata['total_operations']}');
      log('   Categories: ${metadata['categories']}');

      if (metadata['category_stats'] != null) {
        log('   Category Breakdown:');
        for (final entry in metadata['category_stats'].entries) {
          log('     ${entry.key}: ${entry.value['count']} records');
        }
      }
    }
  }

  /// Optimize database performance
  Future<void> optimizeDatabase() async {
    final success = await _dataService.optimizeDatabase();
    if (success) {
      log('✅ Database optimized successfully');
    } else {
      log('❌ Database optimization failed');
    }
  }

  /// Create database backup
  Future<void> backupDatabase() async {
    final backupPath = await _dataService.backupDatabase();
    if (backupPath != null) {
      log('✅ Database backed up to: $backupPath');
    } else {
      log('❌ Database backup failed');
    }
  }

  /// Handle real-time data updates
  void _handleDataUpdate(String category, String key, dynamic value) {
    // Update your app's UI based on real-time changes
    switch (category) {
      case 'devices':
        _updateDeviceUI(key, value);
        break;
      case 'user_preferences':
        _updateUserPreferences(key, value);
        break;
      case 'app_config':
        _updateAppConfig(key, value);
        break;
    }
  }

  void _handleDataDeletion(String category, String key) {
    // Handle data deletion in your app
    log('Handling deletion of $category.$key');
  }

  void _updateDeviceUI(String deviceId, dynamic deviceData) {
    // Update device UI in real-time
    log('Updating device UI for $deviceId');
  }

  void _updateUserPreferences(String key, dynamic value) {
    // Update user preferences in real-time
    log('Updating user preference: $key = $value');
  }

  void _updateAppConfig(String key, dynamic value) {
    // Update app configuration in real-time
    log('Updating app config: $key = $value');
  }

  /// Clean up resources
  void dispose() {
    _dataService.dispose();
  }
}

/// Usage example in your Flutter app
/*
class MyApp extends StatefulWidget {
  @override
  _MyAppState createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  final HomeAutomationDataManager _dataManager = HomeAutomationDataManager();

  @override
  void initState() {
    super.initState();
    _dataManager.initialize();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SQLite Home Automation',
      home: Scaffold(
        appBar: AppBar(title: Text('SQLite Data Storage')),
        body: Column(
          children: [
            ElevatedButton(
              onPressed: () => _dataManager.storeDeviceProperties(),
              child: Text('Store Device Data'),
            ),
            ElevatedButton(
              onPressed: () => _dataManager.searchDevices('fan'),
              child: Text('Search Devices'),
            ),
            ElevatedButton(
              onPressed: () => _dataManager.getDatabaseStats(),
              child: Text('Get Database Stats'),
            ),
            ElevatedButton(
              onPressed: () => _dataManager.optimizeDatabase(),
              child: Text('Optimize Database'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _dataManager.dispose();
    super.dispose();
  }
}
*/
