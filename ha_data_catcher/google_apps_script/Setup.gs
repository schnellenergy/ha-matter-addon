/**
 * Google Apps Script Setup & Bootstrap Utilities
 */

function runSetup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) {
    Logger.log("ERROR: No active spreadsheet. This script must be bound to a Google Sheet.");
    return;
  }
  
  Logger.log("Initializing Schnell Home Automation Telemetry Sheets...");
  
  // 1. Create the sheets in the spreadsheet container
  for (var i = 0; i < REQUIRED_SHEETS.length; i++) {
    var name = REQUIRED_SHEETS[i];
    var sheet = ss.getSheetByName(name);
    if (!sheet) {
      sheet = ss.insertSheet(name);
      Logger.log("Created sheet: " + name);
    } else {
      sheet.clear();
      Logger.log("Cleared existing sheet: " + name);
    }
  }
  
  // 2. Clean up any of the old sheets if they exist
  var oldSheets = [
    "Raw_Events", "Device_State_Changes", "Reliability", "Speed", 
    "Usage", "Device_Inventory", "User_Activity", "Sheet1"
  ];
  for (var j = 0; j < oldSheets.length; j++) {
    var oldName = oldSheets[j];
    if (oldName === "Hub1") continue; // keep Hub1
    
    var oldSheet = ss.getSheetByName(oldName);
    if (oldSheet) {
      try {
        ss.deleteSheet(oldSheet);
        Logger.log("Deleted old sheet: " + oldName);
      } catch (e) {
        Logger.log("Note: Could not delete sheet " + oldName + ": " + e.toString());
      }
    }
  }
  
  Logger.log("==========================================================");
  Logger.log("SUCCESS: Telemetry tables are initialized!");
  Logger.log("Spreadsheet URL: " + ss.getUrl());
  Logger.log("==========================================================");
  Logger.log("DEPLOYMENT INSTRUCTIONS:");
  Logger.log("1. Click 'Deploy' (top right) -> 'New deployment'");
  Logger.log("2. Select type: 'Web app'");
  Logger.log("3. Set options:");
  Logger.log("   - Description: HA Data Webhook");
  Logger.log("   - Execute as: 'Me (your_google_account)'");
  Logger.log("   - Who has access: 'Anyone'");
  Logger.log("4. Click 'Deploy' and authorize Google permission prompts.");
  Logger.log("5. Copy the generated 'Web app URL' and paste it in the add-on configuration.");
  Logger.log("==========================================================");
}
