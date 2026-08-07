#!/usr/bin/env python3
"""
Firestore Helper for SMASH Hub
Manages IP address storage in Firestore database
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

# Try to import Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    logger.warning('⚠️ Firebase Admin SDK not installed')
    FIREBASE_AVAILABLE = False


class FirestoreHelper:
    """Helper class to manage Firestore operations for hub IP storage"""
    
    def __init__(self):
        self.db = None
        self.initialized = False
        
        if not FIREBASE_AVAILABLE:
            logger.error('❌ Firebase Admin SDK not available')
            return
        
        try:
            # Check if Firebase is already initialized
            try:
                firebase_admin.get_app()
                logger.info('✅ Firebase already initialized')
            except ValueError:
                # Initialize Firebase Admin SDK
                service_account_path = '/firebase-service-account.json'
                
                if not os.path.exists(service_account_path):
                    logger.error(f'❌ Service account file not found: {service_account_path}')
                    return
                
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                logger.info('✅ Firebase initialized successfully')
            
            self.db = firestore.client()
            self.initialized = True
            logger.info('✅ Firestore client ready')
            
        except Exception as e:
            logger.error(f'❌ Failed to initialize Firestore: {e}')
            import traceback
            logger.error(f'Stack trace: {traceback.format_exc()}')
    
    def save_hub_ip(
        self,
        mac_address: str,
        ip_address: str,
        max_retries: int = 3,
        timeout_per_attempt: float = 5.0,
    ) -> bool:
        """
        Save hub IP to Firestore: smash_db/<MAC>/home_ip

        Retries and then verifies by reading the value back. The app cannot
        finish onboarding without this record — it waits on `home_ip` to learn
        the hub URL — so a single unchecked write meant one transient network
        blip left the hub online but the app stuck on a spinner forever.

        Args:
            mac_address: MAC address of the hub (e.g., "DC:A6:32:12:34:56")
            ip_address: Dynamic IP address (e.g., "192.168.1.105")
            max_retries: Attempts before giving up
            timeout_per_attempt: Per-call timeout in seconds

        Returns:
            True if the value is confirmed stored, False otherwise
        """
        if not self.initialized or not self.db:
            logger.error('❌ Firestore not initialized, cannot save IP')
            return False

        doc_ref = self.db.collection('smash_db').document(mac_address)

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f'📝 Saving hub IP, attempt {attempt}/{max_retries} '
                    f'(timeout {timeout_per_attempt}s)'
                )
                doc_ref.set({
                    'home_ip': ip_address,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True, timeout=timeout_per_attempt)

                # Verify: a write that "succeeded" but did not land is exactly
                # the failure mode this method exists to rule out.
                snapshot = doc_ref.get(timeout=timeout_per_attempt)
                stored = snapshot.to_dict().get('home_ip') if snapshot.exists else None
                if stored == ip_address:
                    logger.info(f'✅ Saved IP to Firestore: {mac_address} → {ip_address}')
                    logger.info(f'📍 Firestore path: smash_db/{mac_address}/home_ip')
                    return True

                logger.warning(
                    f'⚠️ Attempt {attempt}: write reported success but read back '
                    f'{stored!r} instead of {ip_address!r}'
                )

            except Exception as e:
                logger.warning(f'⚠️ Attempt {attempt}/{max_retries} failed: {str(e)[:120]}')

            if attempt < max_retries:
                wait_time = 0.5 * attempt  # 0.5s, 1s
                logger.info(f'⏳ Waiting {wait_time}s before retry...')
                time.sleep(wait_time)

        logger.error(f'❌ Failed to save IP to Firestore after {max_retries} attempts')
        return False
    
    def get_hub_ip(self, mac_address: str) -> str:
        """
        Get hub IP from Firestore
        
        Args:
            mac_address: MAC address of the hub
        
        Returns:
            IP address if found, None otherwise
        """
        if not self.initialized or not self.db:
            logger.error('❌ Firestore not initialized, cannot get IP')
            return None
        
        try:
            doc_ref = self.db.collection('smash_db').document(mac_address)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                ip = data.get('home_ip')
                logger.info(f'📡 Retrieved IP from Firestore: {mac_address} → {ip}')
                return ip
            else:
                logger.warning(f'⚠️ No document found for MAC: {mac_address}')
                return None
                
        except Exception as e:
            logger.error(f'❌ Failed to get IP from Firestore: {e}')
            return None
    
    def delete_hub_ip(
        self,
        mac_address: str,
        max_retries: int = 6,
        timeout_per_attempt: float = 3.0,
        overall_timeout: float = 25.0,
    ) -> bool:
        """
        Delete hub IP from Firestore (for network reset), verified.

        Two defects used to make this unreliable, and both mattered because the
        app's "Set Up Network Again" prompt is driven entirely by `home_ip`
        disappearing:

          1. The `return False` sat inside the retry loop, so the very first
             transient failure returned immediately — `max_retries` never had
             any effect.
          2. Nothing verified the delete actually landed.

        Now every attempt is followed by a server-side read-back, and the reset
        caller refuses to proceed until this returns True.

        Args:
            mac_address: MAC address of the hub
            max_retries: Maximum number of attempts
            timeout_per_attempt: Timeout in seconds for each call
            overall_timeout: Hard wall-clock cap across all attempts

        The wall-clock cap matters because `timeout_per_attempt` is only a
        best-effort hint: the gRPC layer under firebase-admin applies its own
        60s deadline with internal retries, so one unlucky attempt overran to a
        full minute and a refused reset took ~80s to report. The button monitor
        is blocked for that whole time.

        Returns:
            True only when `home_ip` is confirmed absent, False otherwise
        """
        if not self.initialized or not self.db:
            logger.error('❌ Firestore not initialized, cannot delete IP')
            return False

        doc_ref = self.db.collection('smash_db').document(mac_address)
        deadline = time.monotonic() + overall_timeout

        for attempt in range(1, max_retries + 1):
            if time.monotonic() >= deadline:
                logger.error(
                    f'❌ Giving up after {overall_timeout:.0f}s wall clock '
                    f'({attempt - 1} attempt(s) made)')
                return False
            try:
                logger.info(
                    f'🔄 Firestore deletion attempt {attempt}/{max_retries} '
                    f'(timeout: {timeout_per_attempt}s)'
                )

                # Delete the home_ip field only, never the document — the app
                # needs the doc to survive so a QR re-scan still resolves.
                doc_ref.update({
                    'home_ip': firestore.DELETE_FIELD,
                    'reset_at': firestore.SERVER_TIMESTAMP
                }, timeout=timeout_per_attempt)

                if self.verify_ip_absent(mac_address, timeout=timeout_per_attempt):
                    logger.info(
                        f'✅ Deleted and verified: smash_db/{mac_address}/home_ip is gone'
                    )
                    logger.info('🔄 Network reset can proceed - app will detect missing IP')
                    return True

                logger.warning(
                    f'⚠️ Attempt {attempt}: delete reported success but home_ip is still present'
                )

            except Exception as e:
                logger.warning(f'⚠️ Attempt {attempt}/{max_retries} failed: {str(e)[:120]}')

            if attempt < max_retries:
                wait_time = min(0.5 * attempt, 2.0)  # 0.5s, 1s, 1.5s, 2s, 2s
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                logger.info(f'⏳ Waiting {wait_time}s before retry...')
                time.sleep(min(wait_time, remaining))

        logger.error(f'❌ Failed to delete IP from Firestore after {max_retries} attempts')
        return False

    def verify_ip_absent(self, mac_address: str, timeout: float = 3.0) -> bool:
        """True when the document has no `home_ip` field.

        Raises on transport failure so callers can tell "confirmed gone" apart
        from "could not reach the server" — the reset path must never treat the
        latter as success.
        """
        doc = self.db.collection('smash_db').document(mac_address).get(timeout=timeout)
        if not doc.exists:
            return True
        return doc.to_dict().get('home_ip') is None
