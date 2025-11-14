# Home Assistant Data Collector Add-on

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield] ![Supports armhf Architecture][armhf-shield] ![Supports armv7 Architecture][armv7-shield] ![Supports i386 Architecture][i386-shield]

This add-on collects Home Assistant events in real-time and sends them to Google Sheets for comprehensive analytics and monitoring.

## About

The Home Assistant Data Collector is a powerful add-on that bridges your Home Assistant instance with Google Sheets, enabling you to:

- 📊 **Analyze Device Usage**: Track how often devices are used and when
- 🔍 **Monitor System Performance**: Identify patterns and potential issues
- 📈 **Create Custom Dashboards**: Build analytics dashboards in Google Looker Studio
- 🏠 **Understand Home Patterns**: Analyze automation effectiveness and user behavior
- 📱 **Track Mobile App Usage**: Monitor interactions from different interfaces

## Installation

1. Navigate to the Supervisor in your Home Assistant instance
2. Click on "Add-on Store"
3. Add this repository URL: `https://github.com/your-username/ha-addons`
4. Find "Home Assistant Data Collector" and click "Install"
5. Configure the add-on (see Configuration section below)
6. Start the add-on

## Configuration

### Step 1: Create Google Apps Script

1. Go to [Google Apps Script](https://script.google.com)
2. Create a new project
3. Replace the default code with the provided `google_apps_script.js`
4. Save the project
5. Click "Deploy" → "New Deployment"
6. Choose "Web app" as the type
7. Set "Execute as" to "Me"
8. Set "Who has access" to "Anyone"
9. Click "Deploy" and copy the Web App URL

### Step 2: Get Home Assistant Token

1. In Home Assistant, go to your Profile (click your name in the sidebar)
2. Scroll down to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Give it a name like "Data Collector"
5. Copy the generated token

### Step 3: Configure the Add-on

```yaml
google_sheets_url: "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"
ha_token: "YOUR_LONG_LIVED_ACCESS_TOKEN"
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

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `google_sheets_url` | string | **Required** | Your Google Apps Script Web App URL |
| `ha_token` | string | **Required** | Home Assistant Long-Lived Access Token |
| `collect_historical` | boolean | `true` | Collect existing historical data on startup |
| `batch_size` | integer | `100` | Number of events to process in batch |
| `retry_attempts` | integer | `3` | Number of retry attempts for failed requests |
| `log_level` | string | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `excluded_domains` | list | `[]` | List of domains to exclude from collection |
| `excluded_entities` | list | `[]` | List of specific entities to exclude |
| `include_attributes` | boolean | `true` | Include entity attributes in collected data |

## Data Structure

The add-on collects the following information for each event:

- **Event Metadata**: Unique ID, timestamp, event type
- **Entity Information**: Entity ID, domain, device ID, area ID
- **State Changes**: Old state, new state, attributes
- **User Context**: User ID, automation ID, source
- **Service Calls**: Domain, service name, service data

## Monitoring

### Web Interface

Access the monitoring interface at `http://homeassistant.local:8099` to view:

- Real-time statistics (events processed, sent, errors)
- Success rate and performance metrics
- Recent activity log
- Google Sheets connection testing

### Logs

Monitor the add-on logs for detailed information:

```bash
# View logs in Home Assistant
Supervisor → Add-ons → Home Assistant Data Collector → Logs
```

## Performance Optimization

### For Large Installations

If you have many entities, consider these optimizations:

1. **Exclude High-Volume Domains**:
   ```yaml
   excluded_domains:
     - "sensor"
     - "binary_sensor"
     - "device_tracker"
   ```

2. **Disable Attributes for Performance**:
   ```yaml
   include_attributes: false
   ```

3. **Reduce Batch Size**:
   ```yaml
   batch_size: 50
   ```

### Google Sheets Limits

- **Daily API Calls**: 20,000 per day
- **Concurrent Requests**: 100 per 100 seconds
- **Sheet Size**: 10 million cells maximum

## Troubleshooting

### Common Issues

**Authentication Failed**
- Verify your Home Assistant token is correct and hasn't expired
- Ensure the token has necessary permissions

**Google Sheets Connection Failed**
- Check your Apps Script Web App URL
- Verify the Apps Script is deployed with correct permissions
- Test the connection using the web interface

**High Memory Usage**
- Reduce `batch_size`
- Add more domains to `excluded_domains`
- Disable `include_attributes`

**Missing Historical Data**
- Ensure `collect_historical` is set to `true`
- Check that the Home Assistant history database is accessible
- Verify excluded domains/entities aren't filtering out desired data

### Debug Mode

Enable debug logging for detailed troubleshooting:

```yaml
log_level: "DEBUG"
```

## Analytics Use Cases

### Google Looker Studio Integration

1. Connect Google Looker Studio to your Google Sheets
2. Create charts for:
   - Device usage patterns over time
   - Most frequently used automations
   - Energy consumption trends
   - User interaction patterns

### Custom Analysis

Use the collected data for:
- Identifying unused devices
- Optimizing automation triggers
- Understanding peak usage times
- Monitoring system reliability

## Support

For issues and feature requests:

1. Check the add-on logs for error details
2. Verify your configuration matches the examples
3. Test the Google Sheets connection using the web interface
4. Create an issue with relevant log entries and configuration

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
