# Home Assistant Data Collector Add-on

This add-on collects Home Assistant events in real-time and sends them to Google Sheets for analytics and monitoring.

## Features

- 🔄 **Real-time Event Collection**: Listens to Home Assistant WebSocket for live events
- 📊 **Historical Data Import**: Collects existing states and history on startup
- 📈 **Google Sheets Integration**: Sends data directly to your Google Sheets via Apps Script
- 🎯 **Smart Filtering**: Configurable domain and entity exclusions
- 🔄 **Retry Logic**: Automatic retry with exponential backoff for failed requests
- 📱 **Web Interface**: Monitor collection status via built-in web UI
- ⚡ **High Performance**: Async processing for minimal impact on Home Assistant

## Installation

1. Add this repository to your Home Assistant Add-on Store
2. Install the "Home Assistant Data Collector" add-on
3. Configure the add-on (see Configuration section)
4. Start the add-on

## Configuration

### Required Settings

- **google_sheets_url**: Your Google Apps Script Web App URL
- **ha_token**: Home Assistant Long-Lived Access Token

### Optional Settings

- **collect_historical**: Collect existing states on startup (default: true)
- **batch_size**: Number of events to process in batch (default: 100)
- **retry_attempts**: Number of retry attempts for failed requests (default: 3)
- **log_level**: Logging level (DEBUG, INFO, WARNING, ERROR)
- **excluded_domains**: List of domains to exclude (e.g., ["sensor", "binary_sensor"])
- **excluded_entities**: List of specific entities to exclude
- **include_attributes**: Include entity attributes in data (default: true)

### Example Configuration

```yaml
google_sheets_url: "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"
ha_token: "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
collect_historical: true
batch_size: 100
retry_attempts: 3
log_level: "INFO"
excluded_domains:
  - "sun"
  - "weather"
excluded_entities:
  - "sensor.uptime"
  - "sensor.date"
include_attributes: true
```

## Google Apps Script Setup

1. Create a new Google Apps Script project
2. Replace the default code with the provided `google_apps_script.js`
3. Deploy as a Web App with the following settings:
   - Execute as: Me
   - Who has access: Anyone
4. Copy the Web App URL to the add-on configuration

## Data Structure

The add-on sends the following data structure to Google Sheets:

| Column | Description |
|--------|-------------|
| event_id | Unique identifier for the event |
| timestamp | When the event occurred |
| event_type | Type of event (state_changed, service_called, etc.) |
| entity_id | Entity that triggered the event |
| domain | Domain of the entity (light, switch, sensor, etc.) |
| service | Service called (for service_called events) |
| old_state | Previous state of the entity |
| new_state | New state of the entity |
| attributes | JSON string of entity attributes |
| user_id | User who triggered the event |
| source | Source of the event (home_assistant) |
| automation_id | Automation that triggered the event |
| device_id | Device identifier |
| area_id | Area identifier |
| platform | Platform/integration name |
| created_at | When the record was created |

## Event Types Collected

- **state_changed**: When entity states change (lights on/off, sensor readings, etc.)
- **service_called**: When services are called (turn on light, set temperature, etc.)
- **automation_triggered**: When automations are triggered
- **script_started**: When scripts are executed

## Web Interface

Access the web interface at `http://homeassistant.local:8099` to monitor:

- Events processed and sent
- Success rate and error count
- Real-time activity log
- Google Sheets connection testing

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify your Home Assistant token is correct
   - Ensure the token has the necessary permissions

2. **Google Sheets Connection Failed**
   - Check your Apps Script Web App URL
   - Verify the Apps Script is deployed correctly
   - Test the connection using the web interface

3. **High Memory Usage**
   - Reduce batch_size
   - Add more domains/entities to exclusion lists
   - Disable include_attributes for large setups

### Logs

Check the add-on logs for detailed error information:
```bash
docker logs addon_ha_data_collector
```

## Performance Considerations

- The add-on processes events asynchronously to minimize impact
- Large Home Assistant installations should use exclusion filters
- Consider disabling attributes collection for high-volume entities
- Monitor Google Sheets API quotas and limits

## Support

For issues and feature requests, please check the add-on logs and create an issue with:
- Add-on configuration (remove sensitive tokens)
- Relevant log entries
- Description of the problem

## License

This add-on is released under the MIT License.
