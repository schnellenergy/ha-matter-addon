# 🚀 Quick Start - Custom Data Storage Add-on

## ⚡ 3-Step Installation

### 1️⃣ Copy to Home Assistant
Via Samba: Copy `custom_data_storage` folder to `\\homeassistant.local\addon\local\`

### 2️⃣ SSH and Run Diagnostic
```bash
cd /addon/local/custom_data_storage
chmod +x diagnose_addon.sh
./diagnose_addon.sh
```

### 3️⃣ Reload Add-ons
Home Assistant UI: **Settings → Add-ons → ⋮ → Reload**

---

## ✅ What Was Fixed

- ❌ Removed duplicate `config.json` (was causing conflicts)
- ✅ Fixed `config.yaml` formatting
- ✅ Simplified `build.yaml`
- ✅ Added diagnostic tools

---

## 🔍 Not Showing? Run This:

```bash
# Quick diagnostic
cd /addon/local/custom_data_storage
./diagnose_addon.sh

# Check logs
ha supervisor logs | grep -i custom_data_storage

# Force reload
ha supervisor reload
```

---

## 📍 Expected Location

```
/addon/local/custom_data_storage/
├── config.yaml          ← ONLY THIS (no config.json!)
├── Dockerfile
├── build.yaml
├── run.sh
├── README.md
└── app/
```

---

## ✅ Success = Add-on appears in "Local add-ons" section

---

## 📖 Full Documentation

- **Installation Guide**: `FIXED_INSTALLATION_STEPS.md`
- **Troubleshooting**: `INSTALLATION.md`
- **API Documentation**: `README.md`

