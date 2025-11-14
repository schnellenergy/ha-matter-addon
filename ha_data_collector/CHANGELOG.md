# Changelog

All notable changes to this add-on will be documented in this file.

## [1.0.0] - 2025-01-08

### Added
- Initial release of Home Assistant Data Collector
- Real-time event collection via WebSocket
- Historical data collection on startup
- Google Sheets integration via Apps Script
- Web interface for monitoring
- Configurable filtering and exclusions
- Retry logic with exponential backoff
- Support for multiple event types:
  - state_changed
  - service_called
  - automation_triggered
  - script_started

### Features
- Async processing for high performance
- Smart filtering to reduce noise
- Comprehensive error handling
- Built-in connection testing
- Real-time statistics and monitoring
- Configurable batch processing
- Support for all Home Assistant architectures

### Configuration Options
- Google Sheets URL configuration
- Home Assistant token authentication
- Historical data collection toggle
- Batch size configuration
- Retry attempt settings
- Log level configuration
- Domain and entity exclusions
- Attribute inclusion settings
