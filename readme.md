# CHIP Tool API Server

This project provides a simple Flask-based HTTP API wrapper around the [Connected Home over IP (CHIP)](https://github.com/project-chip/connectedhomeip) command-line tool `chip-tool`. It allows you to trigger CHIP commands via HTTP requests.

---

## 📦 Features

- HTTP API to run `chip-tool` commands
- JSON request/response format
- Easily integratable with other services or frontends
- Docker-compatible setup

---

## 🛠 Requirements

- Python 3.6+
- `chip-tool` binary compiled and available (e.g., inside `connected_home_ip/out/...`)
- Flask and Flask-CORS Python packages

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/chip-tool-addon-python-server.git
cd chip-tool-addon-python-server
