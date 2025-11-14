// Example Flutter service for integrating with the Schnell Custom Metrics Add-on
// Add this to your lib/services/ directory

import 'package:dio/dio.dart';
import 'dart:convert';
import 'dart:developer' as developer;

class SchnellMetricsService {
  static const String _baseUrl = 'http://192.168.6.166:8080/api/v1';
  late final Dio _dio;
  
  SchnellMetricsService() {
    _dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {
        'Content-Type': 'application/json',
      },
    ));
    
    // Add interceptor for logging
    _dio.interceptors.add(LogInterceptor(
      requestBody: true,
      responseBody: true,
      logPrint: (obj) => developer.log(obj.toString(), name: 'MetricsAPI'),
    ));
  }

  // Device Analytics Methods
  Future<bool> logDeviceAnalytic({
    required String deviceId,
    String? deviceName,
    String? deviceType,
    required String metricType,
    String? metricValue,
    double? numericValue,
    String? unit,
  }) async {
    try {
      await _dio.post('/analytics/device', data: {
        'device_id': deviceId,
        'device_name': deviceName,
        'device_type': deviceType,
        'metric_type': metricType,
        'metric_value': metricValue,
        'numeric_value': numericValue,
        'unit': unit,
        'timestamp': DateTime.now().toIso8601String(),
      });
      return true;
    } catch (e) {
      developer.log('Failed to log device analytic: $e', name: 'MetricsAPI');
      return false;
    }
  }

  Future<Map<String, dynamic>?> getDeviceAnalytics({
    String? deviceId,
    String? metricType,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 100,
  }) async {
    try {
      final response = await _dio.get('/analytics/device', 
        queryParameters: {
          if (deviceId != null) 'device_id': deviceId,
          if (metricType != null) 'metric_type': metricType,
          if (startDate != null) 'start_date': startDate.toIso8601String(),
          if (endDate != null) 'end_date': endDate.toIso8601String(),
          'page': page,
          'page_size': pageSize,
        }
      );
      return response.data;
    } catch (e) {
      developer.log('Failed to get device analytics: $e', name: 'MetricsAPI');
      return null;
    }
  }

  // Performance Metrics Methods
  Future<bool> logPerformanceMetric({
    required String metricName,
    required String metricCategory,
    required double value,
    String? unit,
    String? deviceId,
    int? responseTimeMs,
    double? successRate,
    int? errorCount,
    Map<String, dynamic>? metadata,
  }) async {
    try {
      await _dio.post('/analytics/performance', data: {
        'metric_name': metricName,
        'metric_category': metricCategory,
        'value': value,
        'unit': unit,
        'device_id': deviceId,
        'response_time_ms': responseTimeMs,
        'success_rate': successRate,
        'error_count': errorCount,
        'metadata': metadata,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log performance metric: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Matter Binding Methods
  Future<bool> logMatterBinding({
    required String bindingName,
    required String sourceDeviceId,
    required String targetDeviceId,
    int? sourceNodeId,
    int? targetNodeId,
    int sourceEndpoint = 1,
    int targetEndpoint = 1,
    String? clusterId,
    String bindingType = 'matter',
    String status = 'active',
    Map<String, dynamic>? metadata,
  }) async {
    try {
      await _dio.post('/bindings/matter', data: {
        'binding_name': bindingName,
        'source_device_id': sourceDeviceId,
        'target_device_id': targetDeviceId,
        'source_node_id': sourceNodeId,
        'target_node_id': targetNodeId,
        'source_endpoint': sourceEndpoint,
        'target_endpoint': targetEndpoint,
        'cluster_id': clusterId,
        'binding_type': bindingType,
        'status': status,
        'metadata': metadata,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log Matter binding: $e', name: 'MetricsAPI');
      return false;
    }
  }

  Future<Map<String, dynamic>?> getMatterBindings({
    String? sourceDeviceId,
    String? targetDeviceId,
    String? status,
    int page = 1,
    int pageSize = 100,
  }) async {
    try {
      final response = await _dio.get('/bindings/matter', 
        queryParameters: {
          if (sourceDeviceId != null) 'source_device_id': sourceDeviceId,
          if (targetDeviceId != null) 'target_device_id': targetDeviceId,
          if (status != null) 'status': status,
          'page': page,
          'page_size': pageSize,
        }
      );
      return response.data;
    } catch (e) {
      developer.log('Failed to get Matter bindings: $e', name: 'MetricsAPI');
      return null;
    }
  }

  Future<bool> updateMatterBindingStatus(int bindingId, String status) async {
    try {
      await _dio.put('/bindings/matter/$bindingId', data: {
        'status': status,
      });
      return true;
    } catch (e) {
      developer.log('Failed to update Matter binding: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Usage Analytics Methods
  Future<bool> logUsageAnalytic({
    String? userId,
    required String actionType,
    String? entityId,
    String? entityType,
    String? actionDetails,
    String? appVersion,
    String? platform,
    String? sessionId,
    int? durationMs,
  }) async {
    try {
      await _dio.post('/analytics/usage', data: {
        'user_id': userId,
        'action_type': actionType,
        'entity_id': entityId,
        'entity_type': entityType,
        'action_details': actionDetails,
        'app_version': appVersion,
        'platform': platform,
        'session_id': sessionId,
        'duration_ms': durationMs,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log usage analytic: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Reliability Metrics Methods
  Future<bool> logReliabilityMetric({
    required String deviceId,
    String? deviceName,
    String? connectionType,
    double? uptimePercentage,
    int? downtimeDurationMinutes,
    DateTime? lastSeen,
    double? connectivityScore,
    double? errorRate,
    int? recoveryTimeMs,
    String status = 'online',
  }) async {
    try {
      await _dio.post('/analytics/reliability', data: {
        'device_id': deviceId,
        'device_name': deviceName,
        'connection_type': connectionType,
        'uptime_percentage': uptimePercentage,
        'downtime_duration_minutes': downtimeDurationMinutes,
        'last_seen': lastSeen?.toIso8601String(),
        'connectivity_score': connectivityScore,
        'error_rate': errorRate,
        'recovery_time_ms': recoveryTimeMs,
        'status': status,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log reliability metric: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Speed Metrics Methods
  Future<bool> logSpeedMetric({
    required String operationType,
    String? deviceId,
    String? commandType,
    DateTime? requestTime,
    DateTime? responseTime,
    int? latencyMs,
    double? throughputMbps,
    double? packetLossPercentage,
    String? networkType,
    bool success = true,
    String? errorMessage,
  }) async {
    try {
      await _dio.post('/analytics/speed', data: {
        'operation_type': operationType,
        'device_id': deviceId,
        'command_type': commandType,
        'request_time': requestTime?.toIso8601String(),
        'response_time': responseTime?.toIso8601String(),
        'latency_ms': latencyMs,
        'throughput_mbps': throughputMbps,
        'packet_loss_percentage': packetLossPercentage,
        'network_type': networkType,
        'success': success,
        'error_message': errorMessage,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log speed metric: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Automation Analytics Methods
  Future<bool> logAutomationAnalytic({
    required String automationId,
    String? automationName,
    String? triggerType,
    String? triggerDetails,
    int? executionTimeMs,
    bool success = true,
    String? errorMessage,
    String? affectedEntities,
    String? userId,
  }) async {
    try {
      await _dio.post('/analytics/automation', data: {
        'automation_id': automationId,
        'automation_name': automationName,
        'trigger_type': triggerType,
        'trigger_details': triggerDetails,
        'execution_time_ms': executionTimeMs,
        'success': success,
        'error_message': errorMessage,
        'affected_entities': affectedEntities,
        'user_id': userId,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log automation analytic: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Scene Analytics Methods
  Future<bool> logSceneAnalytic({
    required String sceneId,
    String? sceneName,
    String? activationMethod,
    int? executionTimeMs,
    int? entitiesCount,
    bool success = true,
    String? errorMessage,
    String? userId,
  }) async {
    try {
      await _dio.post('/analytics/scene', data: {
        'scene_id': sceneId,
        'scene_name': sceneName,
        'activation_method': activationMethod,
        'execution_time_ms': executionTimeMs,
        'entities_count': entitiesCount,
        'success': success,
        'error_message': errorMessage,
        'user_id': userId,
      });
      return true;
    } catch (e) {
      developer.log('Failed to log scene analytic: $e', name: 'MetricsAPI');
      return false;
    }
  }

  // Utility Methods
  Future<Map<String, dynamic>?> getHealthStatus() async {
    try {
      final response = await _dio.get('/health');
      return response.data;
    } catch (e) {
      developer.log('Failed to get health status: $e', name: 'MetricsAPI');
      return null;
    }
  }

  Future<Map<String, dynamic>?> getDatabaseStats() async {
    try {
      final response = await _dio.get('/stats');
      return response.data;
    } catch (e) {
      developer.log('Failed to get database stats: $e', name: 'MetricsAPI');
      return null;
    }
  }

  Future<bool> createBackup() async {
    try {
      await _dio.post('/backup');
      return true;
    } catch (e) {
      developer.log('Failed to create backup: $e', name: 'MetricsAPI');
      return false;
    }
  }

  Future<Map<String, dynamic>?> getAggregatedData({
    required String metricName,
    String aggregationType = 'avg',
    String? groupBy,
    String timeBucket = 'hour',
    DateTime? startDate,
    DateTime? endDate,
  }) async {
    try {
      final response = await _dio.post('/analytics/aggregate', data: {
        'metric_name': metricName,
        'aggregation_type': aggregationType,
        'group_by': groupBy,
        'time_bucket': timeBucket,
        'start_date': startDate?.toIso8601String(),
        'end_date': endDate?.toIso8601String(),
      });
      return response.data;
    } catch (e) {
      developer.log('Failed to get aggregated data: $e', name: 'MetricsAPI');
      return null;
    }
  }
}
