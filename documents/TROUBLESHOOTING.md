# 🔧 Troubleshooting: Addon Not Showing in Home Assistant

## ✅ Your Addon Structure is Valid!

All required files are present and properly configured. If the addon isn't showing up, follow these steps:

## 🎯 Step-by-Step Installation

### Step 1: Verify Your Home Assistant Type

First, determine which type of Home Assistant you're running:

```bash
# Check if you have the 'ha' command
ha --version
```

- **If command works**: You have Home Assistant OS or Supervised
- **If command not found**: You have Home Assistant Container or Core

### Step 2: Copy to Correct Location

#### For Home Assistant OS (most common):

```bash
# The addon should be in:
/usr/share/hassio/addons/local/custom_data_storage/

# Copy command:
sudo mkdir -p /usr/share/hassio/addons/local/custom_data_storage
sudo cp -r /path/to/your/addon/* /usr/share/hassio/addons/local/custom_data_storage/
```

#### For Home Assistant Supervised:

```bash
# The addon should be in:
/addons/custom_data_storage/

# Copy command:
sudo mkdir -p /addons/custom_data_storage
sudo cp -r /path/to/your/addon/* /addons/custom_data_storage/
```

#### For Home Assistant Container:

```bash
# The addon should be in your config directory:
<your-ha-config-path>/addons/custom_data_storage/

# Example:
mkdir -p /home/user/homeassistant/addons/custom_data_storage
cp -r /path/to/your/addon/* /home/user/homeassistant/addons/custom_data_storage/
```

### Step 3: Verify Files Are in Place

```bash
# Check if files exist (adjust path for your installation):
ls -la /usr/share/hassio/addons/local/custom_data_storage/

# You should see:
# - config.json
# - config.yaml
# - Dockerfile
# - build.yaml
# - run.sh
# - app/ (directory)
```

### Step 4: Reload Supervisor

#### Method 1: Using CLI (Recommended)

```bash
ha supervisor reload
```

#### Method 2: Using Home Assistant UI

1. Go to **Settings** → **Add-ons**
2. Click the **⋮** (three dots) in the top right
3. Click **"Reload"** or **"Check for updates"**

#### Method 3: Restart Supervisor Service

```bash
sudo systemctl restart hassio-supervisor
```

Wait 30-60 seconds after reloading.

### Step 5: Check for the Addon

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Scroll down to **"Local add-ons"** section
3. Look for **"Custom Data Storage"**

## 🐛 Still Not Showing? Check Logs

### Check Supervisor Logs

```bash
ha supervisor logs
```

Look for errors related to:

- `custom_data_storage`
- JSON parsing errors
- Docker build errors

### Check System Logs

```bash
journalctl -u hassio-supervisor -f
```

### Common Error Messages and Solutions

#### Error: "Invalid config.json"

- **Solution**: Validate JSON syntax

```bash
python3 -c "import json; json.load(open('config.json'))"
```

#### Error: "Dockerfile not found"

- **Solution**: Ensure Dockerfile is in the addon root directory

#### Error: "Slug already exists"

- **Solution**: Change the slug in config.json to something unique like `custom_data_storage_v2`

#### Error: "Architecture not supported"

- **Solution**: Check that your architecture is in the `arch` list in config.json

## 🔍 Verification Checklist

- [ ] Files are in the correct directory for your HA installation type
- [ ] Directory name matches the slug: `custom_data_storage`
- [ ] config.json exists and is valid JSON
- [ ] Dockerfile exists in the addon root
- [ ] Supervisor has been reloaded
- [ ] Waited at least 60 seconds after reload
- [ ] Checked supervisor logs for errors

## 🚀 Alternative: Use the Install Script

If manual installation isn't working, try the automated script:

```bash
cd /path/to/your/addon
sudo ./install.sh
```

This script will:

1. Detect your Home Assistant installation
2. Copy files to the correct location
3. Set proper permissions
4. Reload the supervisor

## 📝 Manual Verification Commands

```bash
# 1. Check if addon directory exists
ls -la /usr/share/hassio/addons/local/ | grep custom

# 2. Check config.json content
cat /usr/share/hassio/addons/local/custom_data_storage/config.json

# 3. Check supervisor status
ha supervisor info

# 4. List all addons (including local)
ha addons

# 5. Check if Docker can access the Dockerfile
docker build -t test /usr/share/hassio/addons/local/custom_data_storage/
```

## 🆘 Last Resort: Restart Home Assistant

If nothing else works:

```bash
# Full system restart
ha host reboot

# Or just restart Home Assistant
ha core restart
```

## 💡 Tips

1. **Directory name must match slug**: The folder name should be `custom_data_storage`
2. **No spaces in paths**: Avoid spaces in directory names
3. **Permissions**: Ensure files are readable by the hassio user
4. **Case sensitive**: Linux is case-sensitive, ensure exact naming
5. **Wait time**: Give the supervisor 60 seconds to scan for new addons

## 📞 Getting More Help

If the addon still doesn't appear, provide these details:

1. Your Home Assistant installation type (OS/Supervised/Container/Core)
2. Output of `ha supervisor logs`
3. Output of `ls -la /usr/share/hassio/addons/local/custom_data_storage/`
4. Your Home Assistant version: `ha core info`
