/**
 * Google Apps Script Webhook Entry Point
 * 
 * This script runs inside a Google Sheet container.
 * It receives batch event payloads from the Home Assistant Data Collector Add-on
 * and logs them to the appropriate spreadsheets.
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return createJsonResponse({
        status: "error",
        message: "Empty request body"
      }, 400);
    }
    
    // Parse the JSON request payload
    var payload = JSON.parse(e.postData.contents);
    
    // Route to webhook coordinator
    var result = handleWebhook(payload);
    
    return createJsonResponse(result, result.status === "success" ? 200 : 500);
    
  } catch (err) {
    Logger.log("doPost Error: " + err.toString());
    return createJsonResponse({
      status: "error",
      message: "Internal script execution error: " + err.toString()
    }, 500);
  }
}

function doGet(e) {
  return createJsonResponse({
    status: "healthy",
    message: "Google Apps Script webhook is active and listening",
    timestamp: new Date().toISOString()
  }, 200);
}

/**
 * Utility to format JSON outputs for HTTP responses.
 */
function createJsonResponse(data, statusCode) {
  var output = ContentService.createTextOutput(JSON.stringify(data));
  output.setMimeType(ContentService.MimeType.JSON);
  return output;
}
