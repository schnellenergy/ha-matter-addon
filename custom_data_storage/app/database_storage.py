#!/usr/bin/env python3
"""
Database Storage Manager for Custom Data Storage Add-on
Provides SQLite-based storage for handling large amounts of data efficiently
"""

import sqlite3
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseStorage:
    """SQLite-based storage manager for large-scale data"""
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_file = self.storage_path / 'custom_data.db'
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database with required tables"""
        try:
            with self.get_connection() as conn:
                # Create main data table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS custom_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        value_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(category, key)
                    )
                ''')
                
                # Create indexes for performance
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_category_key 
                    ON custom_data(category, key)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_category 
                    ON custom_data(category)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_updated_at 
                    ON custom_data(updated_at)
                ''')
                
                # Create metadata table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                ''')
                
                # Initialize metadata
                self._init_metadata(conn)
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def _init_metadata(self, conn):
        """Initialize metadata table"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Check if metadata exists
        cursor = conn.execute("SELECT COUNT(*) FROM metadata WHERE key = 'created_at'")
        if cursor.fetchone()[0] == 0:
            # First time setup
            metadata_items = [
                ('created_at', timestamp),
                ('last_updated', timestamp),
                ('total_operations', '0'),
                ('version', '2.0.0'),
                ('storage_type', 'sqlite')
            ]
            
            conn.executemany(
                "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                [(key, value, timestamp) for key, value in metadata_items]
            )
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper error handling"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_file,
                timeout=30.0,  # 30 second timeout
                isolation_level=None  # Autocommit mode
            )
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and performance
            conn.execute("PRAGMA cache_size=10000")  # 10MB cache
            conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def set_value(self, key: str, value: Any, category: str = 'default') -> Dict[str, Any]:
        """Set a custom value with optimized database operations"""
        timestamp = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False)
        value_type = type(value).__name__
        
        try:
            with self.get_connection() as conn:
                # Use INSERT OR REPLACE for atomic upsert
                conn.execute('''
                    INSERT OR REPLACE INTO custom_data 
                    (category, key, value, value_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM custom_data WHERE category = ? AND key = ?), ?),
                        ?)
                ''', (category, key, value_json, value_type, category, key, timestamp, timestamp))
                
                # Update metadata
                self._update_metadata(conn, 'last_updated', timestamp)
                self._increment_metadata(conn, 'total_operations')
                
                logger.debug(f"Set value: {category}.{key}")
                
                return {
                    'success': True,
                    'category': category,
                    'key': key,
                    'value': value,
                    'timestamp': timestamp
                }
                
        except Exception as e:
            logger.error(f"Error setting value {category}.{key}: {e}")
            raise
    
    def get_value(self, key: str, category: str = 'default') -> Optional[Any]:
        """Get a custom value with optimized query"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT value FROM custom_data WHERE category = ? AND key = ?",
                    (category, key)
                )
                row = cursor.fetchone()
                
                if row:
                    return json.loads(row[0])
                return None
                
        except Exception as e:
            logger.error(f"Error getting value {category}.{key}: {e}")
            return None
    
    def get_all_values(self, category: str = None) -> Dict[str, Any]:
        """Get all values or values in a specific category"""
        try:
            with self.get_connection() as conn:
                if category:
                    cursor = conn.execute(
                        "SELECT key, value FROM custom_data WHERE category = ? ORDER BY key",
                        (category,)
                    )
                    return {
                        row[0]: json.loads(row[1]) for row in cursor.fetchall()
                    }
                else:
                    cursor = conn.execute(
                        "SELECT category, key, value FROM custom_data ORDER BY category, key"
                    )
                    result = {}
                    for cat, key, value in cursor.fetchall():
                        if cat not in result:
                            result[cat] = {}
                        result[cat][key] = json.loads(value)
                    return result
                    
        except Exception as e:
            logger.error(f"Error getting all values: {e}")
            return {}
    
    def delete_value(self, key: str, category: str = 'default') -> bool:
        """Delete a custom value"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM custom_data WHERE category = ? AND key = ?",
                    (category, key)
                )
                
                if cursor.rowcount > 0:
                    timestamp = datetime.now(timezone.utc).isoformat()
                    self._update_metadata(conn, 'last_updated', timestamp)
                    self._increment_metadata(conn, 'total_operations')
                    logger.debug(f"Deleted value: {category}.{key}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error deleting value {category}.{key}: {e}")
            return False
    
    def search_values(self, search_term: str, category: str = None) -> List[Dict[str, Any]]:
        """Search for values containing the search term"""
        try:
            with self.get_connection() as conn:
                if category:
                    cursor = conn.execute('''
                        SELECT category, key, value, updated_at 
                        FROM custom_data 
                        WHERE category = ? AND (key LIKE ? OR value LIKE ?)
                        ORDER BY updated_at DESC
                        LIMIT 100
                    ''', (category, f'%{search_term}%', f'%{search_term}%'))
                else:
                    cursor = conn.execute('''
                        SELECT category, key, value, updated_at 
                        FROM custom_data 
                        WHERE key LIKE ? OR value LIKE ?
                        ORDER BY updated_at DESC
                        LIMIT 100
                    ''', (f'%{search_term}%', f'%{search_term}%'))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'category': row[0],
                        'key': row[1],
                        'value': json.loads(row[2]),
                        'updated_at': row[3]
                    })
                return results
                
        except Exception as e:
            logger.error(f"Error searching values: {e}")
            return []
    
    def get_categories(self) -> List[str]:
        """Get list of all categories"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT DISTINCT category FROM custom_data ORDER BY category")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return []
    
    def get_category_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for each category"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute('''
                    SELECT 
                        category,
                        COUNT(*) as count,
                        MIN(created_at) as first_created,
                        MAX(updated_at) as last_updated
                    FROM custom_data 
                    GROUP BY category
                    ORDER BY category
                ''')
                
                stats = {}
                for row in cursor.fetchall():
                    stats[row[0]] = {
                        'count': row[1],
                        'first_created': row[2],
                        'last_updated': row[3]
                    }
                return stats
                
        except Exception as e:
            logger.error(f"Error getting category stats: {e}")
            return {}
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get storage metadata with database statistics"""
        try:
            with self.get_connection() as conn:
                # Get metadata
                cursor = conn.execute("SELECT key, value FROM metadata")
                metadata = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Get database statistics
                cursor = conn.execute("SELECT COUNT(*) FROM custom_data")
                total_values = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(DISTINCT category) FROM custom_data")
                total_categories = cursor.fetchone()[0]
                
                # Get database file size
                db_size_bytes = self.db_file.stat().st_size if self.db_file.exists() else 0
                db_size_mb = db_size_bytes / (1024 * 1024)
                
                return {
                    'created_at': metadata.get('created_at'),
                    'last_updated': metadata.get('last_updated'),
                    'total_operations': int(metadata.get('total_operations', 0)),
                    'version': metadata.get('version'),
                    'storage_type': metadata.get('storage_type'),
                    'total_values': total_values,
                    'total_categories': total_categories,
                    'categories': self.get_categories(),
                    'database_size_mb': round(db_size_mb, 3),
                    'database_file': str(self.db_file),
                    'category_stats': self.get_category_stats()
                }
                
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return {}
    
    def _update_metadata(self, conn, key: str, value: str):
        """Update metadata value"""
        timestamp = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, timestamp)
        )
    
    def _increment_metadata(self, conn, key: str):
        """Increment metadata counter"""
        timestamp = datetime.now(timezone.utc).isoformat()
        conn.execute('''
            INSERT OR REPLACE INTO metadata (key, value, updated_at) 
            VALUES (?, CAST((SELECT COALESCE(value, '0') FROM metadata WHERE key = ?) AS INTEGER) + 1, ?)
        ''', (key, key, timestamp))
    
    def vacuum_database(self):
        """Optimize database (vacuum and analyze)"""
        try:
            with self.get_connection() as conn:
                conn.execute("VACUUM")
                conn.execute("ANALYZE")
            logger.info("Database optimized successfully")
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
    
    def backup_database(self, backup_path: str) -> bool:
        """Create database backup"""
        try:
            backup_file = Path(backup_path)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            
            with self.get_connection() as source:
                with sqlite3.connect(backup_file) as backup:
                    source.backup(backup)
            
            logger.info(f"Database backed up to {backup_file}")
            return True
        except Exception as e:
            logger.error(f"Error backing up database: {e}")
            return False
