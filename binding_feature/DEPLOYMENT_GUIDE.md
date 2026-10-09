# Schnell Custom Metrics Add-on - Deployment Guide

This guide provides step-by-step instructions for deploying the Schnell Custom Metrics Add-on to your Home Assistant OS.

## Quick Start

### Option 1: Automated Installation (Recommended)

1. **Copy the add-on files** to your Home Assistant system:
   ```bash
   scp -r custom_metrics_addon/ root@homeassistant.local:/tmp/
   ```

2. **SSH into Home Assistant** and run the installer:
   ```bash
   ssh root@homeassistant.local
   cd /tmp/custom_metrics_addon
   ./install.sh
   ```

3. **Install via Home Assistant UI**:
   - Go to **Settings** → **Add-ons** → **Add-on Store**
   - Click **⋮** → **Repositories**
   - Add: `/addons/schnell_custom_metrics`
   - Install "Schnell Custom Metrics Add-on"

### Option 2: Manual Installation

1. **SSH into Home Assistant**:
   ```bash
   ssh root@homeassistant.local
   ```

2. **Create add-on directory**:
   ```bash
   mkdir -p /addons/schnell_custom_metrics
   ```

3. **Copy all files** to the directory
4. **Set permissions**:
   ```bash
   chmod +x /addons/schnell_custom_metrics/run.sh
   ```

5. **Install via Home Assistant UI** (same as Option 1, step 3)

## Configuration

### Required Configuration

```yaml
log_level: info
ha_token: "your_long_lived_access_token"
auto_backup: true
backup_interval_hours: 24
```

### Getting a Long-Lived Access Token

1. In Home Assistant, click your **profile** (bottom left)
2. Scroll to **Long-Lived Access Tokens**
3. Click **Create Token**
4. Name it "Schnell Metrics Add-on"
5. Copy the token to your configuration

## Verification

### 1. Check Add-on Status
- Go to **Settings** → **Add-ons** → **Schnell Custom Metrics**
- Verify status is "Running"
- Check logs for any errors

### 2. Test API Endpoints
```bash
# Health check
curl http://homeassistant.local:8080/health

# API documentation
curl http://homeassistant.local:8080/docs

# Database stats
curl http://homeassistant.local:8080/api/v1/stats
```

### 3. Test from Flutter App
```dart
final metricsService = SchnellMetricsService();
final health = await metricsService.getHealthStatus();
print('Add-on status: ${health?['status']}');
```

## Integration with Your Flutter App

### 1. Add the Service
Copy `flutter_integration_example.dart` to your `lib/services/` directory as `schnell_metrics_service.dart`.

### 2. Update Your Existing Services

#### Analytics Service Integration
```dart
// In your existing analytics_service.dart
import 'schnell_metrics_service.dart';

class AnalyticsService {
  final SchnellMetricsService _metricsService = SchnellMetricsService();
  
  Future<void> logDeviceInteraction(String deviceId, String action) async {
    // Your existing analytics code...
    
    // Also log to custom metrics
    await _metricsService.logUsageAnalytic(
      actionType: action,
      entityId: deviceId,
      entityType: 'device',
      platform: 'flutter',
      appVersion: '1.0.0',
    );
  }
}
```

#### Matter Binding Service Integration
```dart
// In your existing matter_binding_service.dart
import 'schnell_metrics_service.dart';

class MatterBindingService {
  final SchnellMetricsService _metricsService = SchnellMetricsService();
  
  Future<bool> createBinding(String sourceId, String targetId) async {
    final startTime = DateTime.now();
    
    try {
      // Your existing binding logic...
      final success = await performBinding(sourceId, targetId);
      
      if (success) {
        // Log successful binding
        await _metricsService.logMatterBinding(
          bindingName: 'Auto-generated binding',
          sourceDeviceId: sourceId,
          targetDeviceId: targetId,
          status: 'active',
        );
      }
      
      return success;
    } catch (e) {
      // Log failed binding
      await _metricsService.logMatterBinding(
        bindingName: 'Failed binding attempt',
        sourceDeviceId: sourceId,
        targetDeviceId: targetId,
        status: 'failed',
        metadata: {'error': e.toString()},
      );
      
      rethrow;
    } finally {
      // Log performance metric
      final duration = DateTime.now().difference(startTime);
      await _metricsService.logPerformanceMetric(
        metricName: 'matter_binding_duration',
        metricCategory: 'binding',
        value: duration.inMilliseconds.toDouble(),
        unit: 'ms',
      );
    }
  }
}
```

#### Performance Monitoring
```dart
// Add to your existing services
class PerformanceMonitor {
  final SchnellMetricsService _metricsService = SchnellMetricsService();
  
  Future<T> measureOperation<T>(
    String operationName,
    Future<T> Function() operation,
  ) async {
    final startTime = DateTime.now();
    
    try {
      final result = await operation();
      
      // Log successful operation
      final duration = DateTime.now().difference(startTime);
      await _metricsService.logPerformanceMetric(
        metricName: operationName,
        metricCategory: 'operation',
        value: duration.inMilliseconds.toDouble(),
        unit: 'ms',
        successRate: 100.0,
      );
      
      return result;
    } catch (e) {
      // Log failed operation
      final duration = DateTime.now().difference(startTime);
      await _metricsService.logPerformanceMetric(
        metricName: operationName,
        metricCategory: 'operation',
        value: duration.inMilliseconds.toDouble(),
        unit: 'ms',
        successRate: 0.0,
        errorCount: 1,
      );
      
      rethrow;
    }
  }
}
```

## Data Collection Examples

### Automatic Device State Monitoring
The add-on automatically collects device state changes via WebSocket. You can also manually log specific events:

```dart
// Log device control action
await metricsService.logDeviceAnalytic(
  deviceId: 'light.living_room',
  deviceName: 'Living Room Light',
  deviceType: 'light',
  metricType: 'user_control',
  metricValue: 'turned_on',
  numericValue: 100.0, // brightness
);

// Log automation execution
await metricsService.logAutomationAnalytic(
  automationId: 'automation.morning_routine',
  automationName: 'Morning Routine',
  triggerType: 'time',
  executionTimeMs: 1500,
  success: true,
);

// Log scene activation
await metricsService.logSceneAnalytic(
  sceneId: 'scene.movie_night',
  sceneName: 'Movie Night',
  activationMethod: 'app_button',
  executionTimeMs: 800,
  entitiesCount: 5,
  success: true,
);
```

### Reliability Monitoring
```dart
// Monitor device reliability
await metricsService.logReliabilityMetric(
  deviceId: 'sensor.temperature',
  deviceName: 'Living Room Temperature',
  connectionType: 'zigbee',
  uptimePercentage: 99.5,
  connectivityScore: 95.0,
  status: 'online',
);
```

### Speed Monitoring
```dart
// Monitor API response times
final requestTime = DateTime.now();
// ... make API call ...
final responseTime = DateTime.now();

await metricsService.logSpeedMetric(
  operationType: 'api_call',
  commandType: 'device_control',
  requestTime: requestTime,
  responseTime: responseTime,
  latencyMs: responseTime.difference(requestTime).inMilliseconds,
  success: true,
);
```

## Data Analysis

### Using the API
```bash
# Get device analytics for the last 24 hours
curl "http://homeassistant.local:8080/api/v1/analytics/device?start_date=2024-01-01T00:00:00Z&end_date=2024-01-02T00:00:00Z"

# Get aggregated performance data
curl -X POST "http://homeassistant.local:8080/api/v1/analytics/aggregate" \
  -H "Content-Type: application/json" \
  -d '{
    "metric_name": "performance.value",
    "aggregation_type": "avg",
    "time_bucket": "hour",
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-01-02T00:00:00Z"
  }'

# Get Matter bindings
curl "http://homeassistant.local:8080/api/v1/bindings/matter?status=active"
```

### Direct Database Access
```bash
# SSH into Home Assistant
ssh root@homeassistant.local

# Access the database
sqlite3 /data/schnell_custom_metrics/db/schnell_metrics.db

# Example queries
SELECT COUNT(*) FROM device_analytics WHERE DATE(timestamp) = DATE('now');
SELECT device_id, COUNT(*) as interactions FROM usage_analytics GROUP BY device_id ORDER BY interactions DESC LIMIT 10;
SELECT AVG(value) as avg_response_time FROM performance_metrics WHERE metric_name = 'api_response_time';
```

## Maintenance

### Backups
- Automatic backups run every 24 hours (configurable)
- Manual backup: `curl -X POST http://homeassistant.local:8080/api/v1/backup`
- Backups stored in `/data/schnell_custom_metrics/backups/`

### Monitoring
- Health check: `curl http://homeassistant.local:8080/health`
- Database stats: `curl http://homeassistant.local:8080/api/v1/stats`
- View logs in Home Assistant Add-on interface

### Data Cleanup
```bash
# Clear old data (use with caution)
curl -X DELETE "http://homeassistant.local:8080/api/v1/data/device_analytics?confirm=true"
```

## Troubleshooting

### Common Issues

1. **Add-on won't start**
   - Check configuration syntax
   - Verify HA token is valid
   - Check available disk space

2. **WebSocket not connecting**
   - Verify HA token has proper permissions
   - Check network connectivity
   - Review add-on logs

3. **API requests failing**
   - Verify add-on is running
   - Check port 8080 accessibility
   - Validate request format

### Getting Help

1. Check add-on logs in Home Assistant
2. Verify configuration
3. Test with curl commands
4. Check database connectivity

## Security Considerations

- The add-on runs on port 8080 (internal network only)
- Long-lived access token should be kept secure
- Database is stored locally on the Home Assistant system
- Regular backups are recommended

## Performance

- SQLite database with optimized indexes
- Automatic cleanup of old backups
- Configurable logging levels
- Efficient WebSocket event processing

This add-on provides a robust foundation for collecting and analyzing custom metrics from your Schnell Home Automation project while maintaining data privacy and security within your local Home Assistant environment.
