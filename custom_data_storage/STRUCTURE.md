# 📁 Custom Data Storage Add-on - Folder Structure

## 🎯 Clean and Organized Structure

```
custom_data_storage/
│
├── 📄 Core Add-on Files (Required by Home Assistant)
│   ├── config.yaml              ← Add-on configuration (REQUIRED)
│   ├── Dockerfile               ← Container build instructions (REQUIRED)
│   ├── build.yaml               ← Build configuration (REQUIRED)
│   ├── run.sh                   ← Startup script (REQUIRED)
│   └── README.md                ← Main documentation (REQUIRED)
│
├── 🔧 Helper Scripts
│   ├── diagnose_addon.sh        ← Run on Home Assistant to diagnose issues
│   ├── fix_installation.sh      ← Validate add-on structure locally
│   ├── fix_addon_location.sh    ← Helper for moving add-on
│   └── install.sh               ← Automated installation script
│
├── 📂 app/                      ← Application code
│   ├── main_fixed.py            ← Main application (used by run.sh)
│   ├── database_storage.py      ← SQLite database handler
│   ├── main.py                  ← Original version
│   └── main_enhanced.py         ← Enhanced version
│
├── 📚 documents/                ← All documentation files
│   ├── README.md                ← Documentation index
│   ├── QUICK_START.md           ← 3-step installation guide
│   ├── FIXED_INSTALLATION_STEPS.md  ← Detailed installation
│   ├── INSTALLATION.md          ← Installation issues & solutions
│   ├── TROUBLESHOOTING.md       ← Common problems
│   ├── DEPLOYMENT_GUIDE.md      ← Deployment best practices
│   ├── SAMBA_INSTALLATION_FIX.md    ← Samba setup guide
│   ├── COMPLETE_SQLITE_DOCUMENTATION.md  ← SQLite details
│   ├── STORAGE_COMPARISON.md    ← Storage options comparison
│   ├── ERRORS_FIXED_SUMMARY.md  ← Fixed errors summary
│   └── usage_documentation      ← API usage examples
│
├── 🧪 tests/                    ← Test scripts
│   ├── test_addon.py            ← Add-on functionality tests
│   ├── test_basic_functionality.py  ← Basic tests
│   ├── test_sqlite_performance.py   ← Performance tests
│   ├── quick_test.sh            ← Quick test script
│   └── verify_addon.sh          ← Verification script
│
└── 📝 examples/                 ← Integration examples
    ├── flutter_integration_example.dart  ← Flutter example
    └── FLUTTER_SQLITE_INTEGRATION.dart   ← Flutter SQLite example
```

## 📋 File Purposes

### Required Files (Don't Delete!)
- **config.yaml** - Home Assistant add-on configuration
- **Dockerfile** - Defines the container image
- **build.yaml** - Build configuration for different architectures
- **run.sh** - Entry point script that starts the application
- **README.md** - Main documentation shown in Home Assistant

### Helper Scripts
- **diagnose_addon.sh** - Run this on Home Assistant via SSH to diagnose issues
- **fix_installation.sh** - Run locally to validate add-on structure before copying
- **install.sh** - Automated installation (optional)

### Application Code
- **app/main_fixed.py** - The actual Python application (Flask + SQLite)
- **app/database_storage.py** - Database operations

### Documentation
All `.md` files are now organized in the `documents/` folder for easy access.

### Tests & Examples
Test scripts and integration examples are in their respective folders.

## ✅ What Changed?

**Before:**
```
custom_data_storage/
├── config.yaml
├── config.json  ← DUPLICATE (removed)
├── Dockerfile
├── QUICK_START.md  ← Cluttered root
├── INSTALLATION.md  ← Cluttered root
├── test_addon.py  ← Cluttered root
├── flutter_integration_example.dart  ← Cluttered root
└── ... (many more files in root)
```

**After:**
```
custom_data_storage/
├── config.yaml  ← Clean!
├── Dockerfile
├── build.yaml
├── run.sh
├── README.md
├── app/
├── documents/  ← All docs here
├── tests/      ← All tests here
└── examples/   ← All examples here
```

## 🎯 Benefits

✅ **Cleaner root folder** - Only essential files visible
✅ **Better organization** - Easy to find documentation, tests, examples
✅ **Home Assistant friendly** - Only required files in root
✅ **Easier maintenance** - Logical folder structure
✅ **No duplicate configs** - Removed config.json

## 📝 Notes

- The `documents/` folder is for reference only and not used by Home Assistant
- The `tests/` and `examples/` folders are optional and can be deleted if not needed
- Only files in the root and `app/` folder are used by the add-on at runtime

