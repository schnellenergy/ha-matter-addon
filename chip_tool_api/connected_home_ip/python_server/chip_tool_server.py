# File: chip_tool_server.py
# Fixed version with better error handling and logging

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import logging

app = Flask(__name__)
CORS(app)  # Allow all origins

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

CHIP_TOOL_PATH = "/app/connected_home_ip/out/chip-tool-linux/chip-tool"


def run_chip_tool(args):
    """Execute chip-tool command with proper error handling"""
    cmd = [CHIP_TOOL_PATH] + args
    logger.info(f"Executing command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        logger.info(f"Command completed with return code: {result.returncode}")
        logger.debug(f"STDOUT: {result.stdout}")
        logger.debug(f"STDERR: {result.stderr}")

        return {
            "success": result.returncode == 0,
            "command": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out: {e}")
        return {
            "success": False,
            "error": "Command timed out after 60 seconds",
            "command": " ".join(cmd)
        }
    except Exception as e:
        logger.error(f"Command failed with exception: {e}")
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(cmd)
        }


@app.route('/bind', methods=['POST'])
def bind_device():
    """Create binding between two Matter devices"""
    data = request.get_json()
    switch_node = str(data.get('switch_node'))
    switch_endpoint = str(data.get('switch_endpoint', 1))
    light_node = str(data.get('light_node'))
    light_endpoint = str(data.get('light_endpoint', 1))

    if not (switch_node and light_node):
        return jsonify({"error": "Missing switch_node or light_node"}), 400

    # 1. accesscontrol write acl command
    acl_json = (
        '[{"fabricIndex": 1, "privilege": 5, "authMode": 2, "subjects": null, "targets": null}, '
        f'{{"fabricIndex": 1, "privilege": 3, "authMode": 2, "subjects": [{switch_node}], "targets": null}}]'
    )

    acl_result = run_chip_tool([
        "accesscontrol", "write", "acl",
        acl_json,
        light_node,
        "0"
    ])

    # 2. binding write binding command
    binding_json = f'[{{"node":{light_node}, "endpoint":{light_endpoint}, "cluster":6}}]'
    binding_result = run_chip_tool([
        "binding", "write", "binding",
        binding_json,
        switch_node,
        switch_endpoint
    ])

    return jsonify({
        "success": acl_result.get("success") and binding_result.get("success"),
        "acl_command": acl_result,
        "binding_command": binding_result
    })


@app.route('/pair', methods=['POST'])
def pair_device():
    """Commission a Matter device"""
    data = request.get_json()
    node_id = str(data.get('node_id'))
    passcode = str(data.get('passcode'))

    if not node_id or not passcode:
        return jsonify({"error": "Missing node_id or passcode"}), 400

    result = run_chip_tool(["pairing", "code", node_id, passcode])
    return jsonify(result)


@app.route('/command', methods=['POST'])
def run_custom_command():
    """Execute custom chip-tool command"""
    data = request.get_json()

    logger.info(f"Received /command request with data: {data}")

    # Validate request data
    if not data:
        logger.error("No JSON data in request")
        return jsonify({"error": "No JSON data in request body"}), 400

    if 'args' not in data:
        logger.error("Missing 'args' in request body")
        return jsonify({"error": "Missing 'args' in request body"}), 400

    args = data['args']

    # Validate args is a list
    if not isinstance(args, list):
        logger.error(f"'args' is not a list: {type(args)}")
        return jsonify({"error": "'args' must be a list of strings"}), 400

    # Validate all args are strings
    if not all(isinstance(arg, str) for arg in args):
        logger.error(f"Not all args are strings: {args}")
        return jsonify({"error": "'args' must be a list of strings"}), 400

    # Validate args is not empty
    if len(args) == 0:
        logger.error("'args' list is empty")
        return jsonify({"error": "'args' list cannot be empty"}), 400

    logger.info(f"Executing custom command with args: {args}")
    result = run_chip_tool(args)
    return jsonify(result)


@app.route('/toggle', methods=['POST'])
def toggle_device():
    """Toggle a Matter device on/off"""
    data = request.get_json()
    node_id = str(data.get('node_id'))
    endpoint = str(data.get('endpoint', 1))  # default to endpoint 1

    if not node_id:
        return jsonify({"error": "Missing node_id"}), 400

    result = run_chip_tool(["onoff", "toggle", node_id, endpoint])
    return jsonify(result)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "chip-tool-api"})


@app.route('/routes', methods=['GET'])
def list_routes():
    """List all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            "endpoint": rule.endpoint,
            "methods": list(rule.methods),
            "path": str(rule.rule)
        })
    return jsonify({"routes": routes})


if __name__ == '__main__':
    logger.info("Starting chip-tool API server on port 6000")
    logger.info("Available routes:")
    for rule in app.url_map.iter_rules():
        logger.info(f"  {rule.rule} - {list(rule.methods)}")
    app.run(host="0.0.0.0", port=6000, debug=True)
