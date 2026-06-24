/**
 * Google Apps Script Webhook Manager
 */

function handleWebhook(payload) {
  // 1. Basic validation
  if (!payload) {
    return {
      status: "error",
      message: "Null payload received"
    };
  }
  
  var hubId = payload.hub_id;
  var events = payload.events;
  
  if (!hubId) {
    return {
      status: "error",
      message: "Missing 'hub_id' parameter in payload"
    };
  }
  
  if (!events || !Array.isArray(events)) {
    return {
      status: "error",
      message: "Missing or invalid 'events' array in payload"
    };
  }
  
  if (events.length === 0) {
    return {
      status: "success",
      message: "Zero events processed (empty array)",
      count: 0
    };
  }
  
  // Log request metrics
  Logger.log("Processing batch from " + hubId + " with " + events.length + " events.");
  
  // 2. Append events to Sheets database
  try {
    var writeResult = writeEventsToSheets(hubId, events);
    return writeResult;
  } catch (e) {
    Logger.log("Error writing events: " + e.toString());
    return {
      status: "error",
      message: "Failed to write events to sheets: " + e.toString()
    };
  }
}
