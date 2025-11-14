# 🔧 Fix: Addon Not Showing (Samba Share Installation)

## ❌ The Problem

When you copy the addon via **Samba share** to `addons/local/`, you're actually copying to:

```
/config/addons/local/custom_data_storage/
```

But **Home Assistant OS** looks for local addons in:

```
/addons/custom_data_storage/
```

These are **different locations**! That's why your addon doesn't appear.

## ✅ The Solution

You need to use **SSH** or the **Terminal & SSH addon** to copy files to the correct location.

### Method 1: Using Terminal & SSH Addon (Easiest)

#### Step 1: Install Terminal & SSH Addon

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Search for **"Terminal & SSH"**
3. Click **Install**
4. Click **Start**
5. Click **"Open Web UI"**

#### Step 2: Create the Addon Directory

In the Terminal, run:

```bash
mkdir -p /addons/custom_data_storage
```

#### Step 3: Copy Files from Config to Addons

```bash
# Copy all files from the Samba location to the correct location
cp -r /config/addons/local/custom_data_storage/* /addons/custom_data_storage/

# Verify files are copied
ls -la /addons/custom_data_storage/
```

You should see:

- config.json
- config.yaml
- Dockerfile
- build.yaml
- run.sh
- app/ (directory)

#### Step 4: Set Permissions

```bash
chmod +x /addons/custom_data_storage/run.sh
```

#### Step 5: Reload Supervisor

```bash
ha supervisor reload
```

Wait 30-60 seconds, then check **Settings** → **Add-ons** → **Add-on Store** → **Local add-ons**

---

### Method 2: Using SSH (If you have SSH access)

```bash
# SSH into your Home Assistant
ssh root@homeassistant.local

# Create addon directory
mkdir -p /addons/custom_data_storage

# Copy files (adjust source path if needed)
cp -r /config/addons/local/custom_data_storage/* /addons/custom_data_storage/

# Set permissions
chmod +x /addons/custom_data_storage/run.sh

# Reload supervisor
ha supervisor reload
```

---

### Method 3: Create a Repository Addon (Alternative)

If you want to use the Samba share location, you need to create a **repository** instead:

#### Step 1: Create repository.json

In `/config/addons/local/`, create a file called `repository.json`:

```json
{
  "name": "Local Custom Addons",
  "url": "https://github.com/yourusername/your-repo",
  "maintainer": "Your Name"
}
```

#### Step 2: Keep your addon in the structure:

```
/config/addons/local/
├── repository.json
└── custom_data_storage/
    ├── config.json
    ├── config.yaml
    ├── Dockerfile
    ├── build.yaml
    ├── run.sh
    └── app/
```

#### Step 3: Add the repository in Home Assistant

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Click **⋮** (three dots) → **Repositories**
3. Add: `file:///config/addons/local`
4. Click **Add**

---

## 🎯 Quick Fix Script

If you have Terminal & SSH addon installed, copy and paste this entire script:

```bash
#!/bin/bash

echo "🔧 Fixing Custom Data Storage Addon Location..."

# Check if source exists
if [ ! -d "/config/addons/local/custom_data_storage" ]; then
    echo "❌ Source not found: /config/addons/local/custom_data_storage"
    echo "Please ensure you copied the addon via Samba first!"
    exit 1
fi

# Create target directory
echo "📁 Creating /addons/custom_data_storage..."
mkdir -p /addons/custom_data_storage

# Copy files
echo "📋 Copying files..."
cp -r /config/addons/local/custom_data_storage/* /addons/custom_data_storage/

# Set permissions
echo "🔐 Setting permissions..."
chmod +x /addons/custom_data_storage/run.sh

# Verify
echo "✅ Verifying installation..."
if [ -f "/addons/custom_data_storage/config.json" ]; then
    echo "✅ config.json found"
else
    echo "❌ config.json not found!"
    exit 1
fi

if [ -f "/addons/custom_data_storage/Dockerfile" ]; then
    echo "✅ Dockerfile found"
else
    echo "❌ Dockerfile not found!"
    exit 1
fi

# Reload supervisor
echo "🔄 Reloading supervisor..."
ha supervisor reload

echo ""
echo "✅ Done! Wait 30-60 seconds, then check:"
echo "   Settings → Add-ons → Add-on Store → Local add-ons"
echo ""
echo "📍 Addon installed at: /addons/custom_data_storage"
```

Save this as `fix_addon_location.sh` and run:

```bash
chmod +x fix_addon_location.sh
./fix_addon_location.sh
```

---

## 🔍 Verify Installation

After copying to the correct location, verify:

```bash
# Check if addon exists in correct location
ls -la /addons/custom_data_storage/

# Check supervisor logs
ha supervisor logs | tail -20

# List all addons
ha addons
```

---

## 📝 Summary

**Wrong Location (via Samba):**

```
/config/addons/local/custom_data_storage/  ❌
```

**Correct Location (for Home Assistant OS):**

```
/addons/custom_data_storage/  ✅
```

**How to Access Correct Location:**

- Use **Terminal & SSH addon** (recommended)
- Use **SSH** if enabled
- Or create a **repository.json** to use the Samba location

---

## 💡 Why This Happens

Home Assistant has two different addon locations:

1. **`/addons/`** - System-level local addons (requires SSH/Terminal)
2. **`/config/addons/`** - Config-level addons (accessible via Samba, but needs repository.json)

When you use Samba, you only see the config directory, not the system directory.

---

## ✅ After Fix

Once you copy to `/addons/custom_data_storage/`, your addon will appear in:
**Settings** → **Add-ons** → **Add-on Store** → **Local add-ons** → **Custom Data Storage**
