#!/usr/bin/with-contenv bashio

# Get config
LOG_LEVEL=$(bashio::config 'log_level')

# Create data directory
mkdir -p /data/matter_controller

# Print some debug info
bashio::log.info "Python version:"
python3 --version
bashio::log.info "Installed packages:"
pip3 list

# Create a simple HTTP server
cat > /tmp/server.py << 'EOF'
import http.server
import socketserver
import json

PORT = 8099

class MatterHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        if self.path == '/':
            response = {"message": "Matter Controller API is running"}
        elif self.path == '/api/devices':
            response = {"devices": []}
        else:
            response = {"error": "Not found"}

        self.wfile.write(json.dumps(response).encode())

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        if self.path == '/api/commission':
            response = {"success": True, "device_id": "mock-device-123", "name": "Mock Device"}
        else:
            response = {"error": "Not found"}

        self.wfile.write(json.dumps(response).encode())

with socketserver.TCPServer(("", PORT), MatterHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
EOF

# Start the HTTP server
bashio::log.info "Starting Matter Controller API on port 8099..."
python3 /tmp/server.py
