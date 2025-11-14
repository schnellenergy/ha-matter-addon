# Installation Guide for Custom Data Storage Add-on

## Problem: Add-on Not Showing in Home Assistant

If you've copied the add-on folder to `/addon/local/` via Samba and it's not showing up, follow these steps:

## ✅ Correct Installation Steps

### Step 1: Verify Folder Structure
The folder structure should be:
```
/addon/local/custom_data_storage/
├── config.yaml          ← REQUIRED (only this, not config.json)
├── Dockerfile           ← REQUIRED
├── build.yaml           ← REQUIRED
├── run.sh              ← REQUIRED
├── README.md           ← REQUIRED
├── icon.png            ← OPTIONAL but recommended
└── app/
    ├── main_fixed.py
    └── database_storage.py
```

### Step 2: Check File Permissions
After copying via Samba, SSH into Home Assistant and run:
```bash
cd /addon/local/custom_data_storage
chmod +x run.sh
chmod 644 config.yaml
chmod 644 Dockerfile
chmod 644 build.yaml
```

### Step 3: Reload Add-ons
You have 3 options:

**Option A: Reload Add-ons (Fastest)**
1. Go to Settings → Add-ons
2. Click the three dots (⋮) in the top right
3. Click "Reload"
4. Wait 10-15 seconds
5. Check "Local add-ons" section

**Option B: Restart Supervisor**
```bash
ha supervisor restart
```

**Option C: Full Restart (Last Resort)**
```bash
ha host reboot
```

### Step 4: Check Supervisor Logs
If still not showing, check logs:
```bash
ha supervisor logs
```

Look for errors related to:
- `custom_data_storage`
- YAML parsing errors
- Docker build errors

## 🔍 Common Issues

### Issue 1: Both config.yaml and config.json exist
**Solution:** Delete `config.json`, keep only `config.yaml`

### Issue 2: Invalid YAML syntax
**Solution:** Ensure proper indentation (2 spaces, no tabs)

### Issue 3: Missing required files
**Solution:** Ensure you have: `config.yaml`, `Dockerfile`, `build.yaml`, `run.sh`, `README.md`

### Issue 4: Wrong folder name
**Solution:** Folder name should match the `slug` in config.yaml: `custom_data_storage`

### Issue 5: Permissions issue
**Solution:** Run `chmod +x run.sh` via SSH

## 📋 Verification Checklist

- [ ] Folder is at `/addon/local/custom_data_storage/`
- [ ] Only `config.yaml` exists (no `config.json`)
- [ ] `run.sh` is executable (`chmod +x run.sh`)
- [ ] All required files are present
- [ ] Supervisor has been reloaded
- [ ] Checked supervisor logs for errors

## 🎯 Quick Fix Script

Run this via SSH to fix common issues:
```bash
cd /addon/local/custom_data_storage
rm -f config.json  # Remove duplicate config
chmod +x run.sh    # Make run script executable
ha supervisor reload  # Reload add-ons
```

## 📞 Still Not Working?

Check the supervisor logs:
```bash
ha supervisor logs | grep -i "custom_data_storage"
```

This will show any errors specific to your add-on.

