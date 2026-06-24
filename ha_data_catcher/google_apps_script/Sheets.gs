/**
 * Google Apps Script Sheets Database Connector
 */

var REQUIRED_SHEETS = [
  "Hub1"
];

function writeEventsToSheets(hubId, events) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) {
    throw new Error("No active spreadsheet linked to this script. Please bind this script to a Google Sheet.");
  }
  
  // 1. Ensure all worksheets exist
  var sheets = {};
  for (var i = 0; i < REQUIRED_SHEETS.length; i++) {
    var name = REQUIRED_SHEETS[i];
    var sheet = ss.getSheetByName(name);
    if (!sheet) {
      sheet = ss.insertSheet(name);
      Logger.log("Auto-created missing sheet: " + name);
    }
    sheets[name] = sheet;
  }
  
  // 2. Fetch or initialize headers in Hub1 sheet
  var rawSheet = sheets["Hub1"];
  var existingHeaders = [];
  
  if (rawSheet.getLastRow() > 0) {
    // Read the existing headers from row 1
    existingHeaders = rawSheet.getRange(1, 1, 1, rawSheet.getLastColumn()).getValues()[0];
  }
  
  // Extract all unique keys present across ALL events in this batch
  var batchKeys = {};
  for (var j = 0; j < events.length; j++) {
    var eventKeys = Object.keys(events[j]);
    for (var k = 0; k < eventKeys.length; k++) {
      batchKeys[eventKeys[k]] = true;
    }
  }
  var uniqueBatchKeys = Object.keys(batchKeys);
  
  // Determine if there are new keys that need to be appended to headers
  var headersUpdated = false;
  var headersMap = {};
  
  // Map existing headers
  for (var h = 0; h < existingHeaders.length; h++) {
    headersMap[existingHeaders[h]] = h;
  }
  
  // Add new headers if any
  for (var b = 0; b < uniqueBatchKeys.length; b++) {
    var key = uniqueBatchKeys[b];
    if (headersMap[key] === undefined) {
      existingHeaders.push(key);
      headersMap[key] = existingHeaders.length - 1;
      headersUpdated = true;
    }
  }
  
  // Write headers back if they were created or updated
  if (headersUpdated || rawSheet.getLastRow() === 0) {
    rawSheet.getRange(1, 1, 1, existingHeaders.length).setValues([existingHeaders]);
    // Format header row (bold & light grey background) for premium feel
    var headerRange = rawSheet.getRange(1, 1, 1, existingHeaders.length);
    headerRange.setFontWeight("bold");
    headerRange.setBackground("#E0E0E0");
  }
  
  // 3. Map events to rows based on current headers schema
  var rows = [];
  for (var eIdx = 0; eIdx < events.length; eIdx++) {
    var event = events[eIdx];
    var row = [];
    for (var colIdx = 0; colIdx < existingHeaders.length; colIdx++) {
      var headerKey = existingHeaders[colIdx];
      var value = event[headerKey];
      
      if (value === undefined || value === null) {
        row.push("");
      } else if (typeof value === "object") {
        row.push(JSON.stringify(value));
      } else {
        row.push(value);
      }
    }
    rows.push(row);
  }
  
  // 4. Batch append rows
  if (rows.length > 0) {
    var startRow = rawSheet.getLastRow() + 1;
    rawSheet.getRange(startRow, 1, rows.length, existingHeaders.length).setValues(rows);
  }
  
  return {
    status: "success",
    message: "Successfully logged batch events to sheets database",
    count: events.length
  };
}
