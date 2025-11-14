# ✅ FIXED - Installation Steps for Custom Data Storage Add-on

## 🔧 What Was Fixed

1. ✅ **Removed duplicate `config.json`** - Home Assistant was confused by having both `config.yaml` and `config.json`
2. ✅ **Updated `config.yaml`** - Added required fields and fixed formatting
3. ✅ **Simplified `build.yaml`** - Removed unnecessary labels that could cause issues
4. ✅ **Verified all required files** - All necessary files are present and properly formatted

## 📦 Installation Steps

### Step 1: Copy the Add-on to Home Assistant

**Via Samba Share:**

1. Open File Explorer (Windows) or Finder (Mac)
2. Connect to your Home Assistant:
   - Windows: `\\homeassistant.local\addon`
   - Mac: `smb://homeassistant.local/addon`
3. Navigate to the `local` folder
4. **Delete the old `custom_data_storage` folder if it exists**
5. Copy the entire `custom_data_storage` folder from this project into the `local` folder

**Final path should be:**
```
\\homeassistant.local\addon\local\custom_data_storage\
```

### Step 2: SSH into Home Assistant

1. Enable SSH add-on if not already enabled
2. SSH into your Home Assistant:
   ```bash
   ssh root@homeassistant.local
   ```

### Step 3: Run the Diagnostic Script

```bash
cd /addon/local/custom_data_storage
chmod +x diagnose_addon.sh
./diagnose_addon.sh
```

This script will:
- ✅ Verify all required files are present
- ✅ Remove any duplicate config.json
- ✅ Fix file permissions
- ✅ Validate config.yaml syntax
- ✅ Check supervisor logs for errors
- ✅ Reload the supervisor

### Step 4: Reload Add-ons in Home Assistant UI

1. Open Home Assistant web interface
2. Go to **Settings** → **Add-ons**
3. Click the **three dots (⋮)** in the top right corner
4. Click **"Reload"**
5. Wait 10-15 seconds

### Step 5: Find and Install the Add-on

1. Scroll down to the **"Local add-ons"** section
2. You should see **"Custom Data Storage"**
3. Click on it
4. Click **"Install"**
5. Wait for installation to complete
6. Click **"Start"**

## 🔍 Troubleshooting

### Add-on Still Not Showing?

**Check 1: Verify folder location**
```bash
ls -la /addon/local/custom_data_storage/
```
You should see: `config.yaml`, `Dockerfile`, `build.yaml`, `run.sh`, `README.md`

**Check 2: Check supervisor logs**
```bash
ha supervisor logs | grep -i custom_data_storage
```

**Check 3: Verify no config.json exists**
```bash
ls -la /addon/local/custom_data_storage/config.*
```
You should ONLY see `config.yaml`, NOT `config.json`

**Check 4: Verify YAML syntax**
```bash
cd /addon/local/custom_data_storage
python3 -c "import yaml; print(yaml.safe_load(open('config.yaml')))"
```

**Check 5: Force reload**
```bash
ha supervisor reload
sleep 5
ha addons
```

### Common Error Messages

**Error: "Add-on config is invalid"**
- Solution: Run `./diagnose_addon.sh` to validate and fix config.yaml

**Error: "Failed to build add-on"**
- Solution: Check Dockerfile syntax and ensure all base images are accessible

**Error: "Add-on not found"**
- Solution: Verify folder name matches slug in config.yaml (should be `custom_data_storage`)

## 📋 Verification Checklist

Before asking for help, verify:

- [ ] Folder is at `/addon/local/custom_data_storage/`
- [ ] Only `config.yaml` exists (no `config.json`)
- [ ] All required files present: `config.yaml`, `Dockerfile`, `build.yaml`, `run.sh`, `README.md`
- [ ] `run.sh` is executable (`ls -la run.sh` shows `-rwxr-xr-x`)
- [ ] Ran `./diagnose_addon.sh` successfully
- [ ] Reloaded add-ons via UI (Settings → Add-ons → ⋮ → Reload)
- [ ] Checked supervisor logs for errors
- [ ] Waited at least 15 seconds after reload

## 🎯 Quick Command Reference

```bash
# Navigate to add-on folder
cd /addon/local/custom_data_storage

# Run diagnostic
./diagnose_addon.sh

# Check logs
ha supervisor logs | grep -i custom_data_storage

# Reload supervisor
ha supervisor reload

# List all add-ons
ha addons

# Restart Home Assistant (last resort)
ha host reboot
```

## ✅ Success Indicators

You'll know it's working when:

1. ✅ Add-on appears in "Local add-ons" section
2. ✅ You can click on it and see the description
3. ✅ "Install" button is available
4. ✅ After installation, "Start" button appears
5. ✅ Add-on starts without errors
6. ✅ Web UI is accessible at `http://homeassistant.local:8100`

## 📞 Still Having Issues?

If the add-on still doesn't show after following all steps:

1. Run the diagnostic script and save the output:
   ```bash
   ./diagnose_addon.sh > diagnostic_output.txt
   ```

2. Check the supervisor logs:
   ```bash
   ha supervisor logs > supervisor_logs.txt
   ```

3. Share both files for further troubleshooting

