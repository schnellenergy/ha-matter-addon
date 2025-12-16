# Firebase Service Account Setup

## Instructions

1. **Download Service Account Key from Firebase Console:**
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Select your project: `schnell-home-automation`
   - Click on Settings (gear icon) → Project Settings
   - Go to "Service Accounts" tab
   - Click "Generate New Private Key"
   - Download the JSON file

2. **Rename and Place the File:**
   - Rename the downloaded file to `firebase-service-account.json`
   - Place it in the `wifi_onboarding/` directory
   - **IMPORTANT:** This file contains sensitive credentials - never commit it to git!

3. **Verify .gitignore:**
   - Ensure `firebase-service-account.json` is in `.gitignore`
   - The example file (`firebase-service-account.json.example`) can be committed

## File Location

```
wifi_onboarding/
├── firebase-service-account.json          ← Your actual credentials (DO NOT COMMIT)
├── firebase-service-account.json.example  ← Template (safe to commit)
└── firestore_helper.py                    ← Uses the credentials
```

## Security Notes

⚠️ **CRITICAL:** The `firebase-service-account.json` file contains private keys that grant full access to your Firebase project. Keep it secure!

- ✅ Add to `.gitignore`
- ✅ Store securely (password manager, secrets vault)
- ✅ Rotate keys if compromised
- ❌ Never commit to version control
- ❌ Never share publicly
- ❌ Never hardcode in source code
