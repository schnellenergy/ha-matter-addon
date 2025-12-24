# Firebase IP Auto-Fetch Setup

The HA Data Collector addon can automatically fetch the Home Assistant IP address from Firebase Firestore.

## How It Works

1. Your `wifi_onboarding` addon updates the IP in Firestore: `smash_db/<MAC_ADDRESS>/home_ip`
2. The `ha_data_collector` addon reads from the same location
3. No manual IP configuration needed!

## Setup Instructions

### 1. Copy Firebase Service Account

Copy your Firebase service account JSON file to this directory:

```bash
cp /path/to/your/firebase-service-account.json ha_data_collector/firebase-service-account.json
```

**Important:** This file contains sensitive credentials. Make sure it's in `.gitignore`!

### 2. Build & Deploy

The addon will automatically:
- Detect the hub's MAC address
- Fetch the IP from `smash_db/<MAC>/home_ip`
- Use that IP to connect to Home Assistant

### 3. Priority Order

The addon uses this priority for determining the HA IP:

1. **Firebase Firestore** (if service account exists)
2. **Manual IP** (from `ha_ip` config field)
3. **homeassistant.local** (fallback)

## Logs

When Firebase is configured, you'll see:

```
🔥 Firebase service account found - attempting to fetch HA IP from Firestore...
📍 Hub MAC Address: 2C:CF:67:6E:11:52
✅ Successfully fetched HA IP from Firebase: 192.168.6.167
🔥 Using IP from Firebase Firestore: 192.168.6.167
```

## Firestore Structure

```
smash_db/
  └── 2C:CF:67:6E:11:52/
      ├── home_ip: "192.168.6.167"
      └── updated_at: <timestamp>
```

## Troubleshooting

If Firebase fetch fails, the addon will automatically fall back to:
1. Manual IP (if configured)
2. `homeassistant.local` hostname

Check logs for:
- `⚠️ Could not fetch IP from Firebase` - Firebase unavailable, using fallback
- `ℹ️ No Firebase service account found` - Service account not copied, using fallback
