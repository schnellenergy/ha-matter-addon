#!/usr/bin/env python3
"""
Firestore Helper for SMASH Hub
Manages IP address storage in Firestore database
"""

import logging
import os

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
    
    def save_hub_ip(self, mac_address: str, ip_address: str) -> bool:
        """
        Save hub IP to Firestore: smash_db/<MAC>/home_ip
        
        Args:
            mac_address: MAC address of the hub (e.g., "DC:A6:32:12:34:56")
            ip_address: Dynamic IP address (e.g., "192.168.1.105")
        
        Returns:
            True if successful, False otherwise
        """
        if not self.initialized or not self.db:
            logger.error('❌ Firestore not initialized, cannot save IP')
            return False
        
        try:
            # Reference to the document: smash_db/<MAC_ADDRESS>
            doc_ref = self.db.collection('smash_db').document(mac_address)
            
            # Set/update the home_ip field
            doc_ref.set({
                'home_ip': ip_address,
                'updated_at': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            logger.info(f'✅ Saved IP to Firestore: {mac_address} → {ip_address}')
            logger.info(f'📍 Firestore path: smash_db/{mac_address}/home_ip')
            return True
            
        except Exception as e:
            logger.error(f'❌ Failed to save IP to Firestore: {e}')
            import traceback
            logger.error(f'Stack trace: {traceback.format_exc()}')
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
    
    def delete_hub_ip(self, mac_address: str, max_retries: int = 3, timeout_per_attempt: float = 3.0) -> bool:
        """
        Delete hub IP from Firestore (for network reset) with retry logic
        
        Args:
            mac_address: MAC address of the hub
            max_retries: Maximum number of retry attempts (default: 3)
            timeout_per_attempt: Timeout in seconds for each attempt (default: 3.0)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.initialized or not self.db:
            logger.error('❌ Firestore not initialized, cannot delete IP')
            return False
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f'🔄 Firestore deletion attempt {attempt}/{max_retries} (timeout: {timeout_per_attempt}s)')
                
                # Reference to the document: smash_db/<MAC_ADDRESS>
                doc_ref = self.db.collection('smash_db').document(mac_address)
                
                # Delete the home_ip field (not the entire document)
                # Use a short timeout to prevent long hangs during network reset
                doc_ref.update({
                    'home_ip': firestore.DELETE_FIELD,
                    'reset_at': firestore.SERVER_TIMESTAMP
                }, timeout=timeout_per_attempt)
                
                logger.info(f'✅ Deleted IP from Firestore for MAC: {mac_address} (attempt {attempt})')
                logger.info(f'🔄 Network reset completed - app will detect missing IP')
                return True
                
            except Exception as e:
                logger.warning(f'⚠️ Attempt {attempt}/{max_retries} failed: {str(e)[:100]}')
                
                if attempt < max_retries:
                    # Wait a bit before retrying (but not too long)
                    import time
                    wait_time = 0.5 * attempt  # 0.5s, 1s, 1.5s
                    logger.info(f'⏳ Waiting {wait_time}s before retry...')
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    logger.error(f'❌ Failed to delete IP from Firestore after {max_retries} attempts')
                    import traceback
                    logger.error(f'Stack trace: {traceback.format_exc()}')
            return False
