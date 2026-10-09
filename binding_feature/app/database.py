import sqlite3
import aiosqlite
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DB_PATH = "/data/db/schnell_storage.db"
BACKUP_PATH = "/data/backups"


class DatabaseManager:
    def __init__(self):
        self.db_path = DB_PATH
        self.backup_path = BACKUP_PATH

    async def init_database(self):
        """Initialize database with all required tables"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Enable foreign keys
                await db.execute("PRAGMA foreign_keys = ON")

                # Create tables
                await self._create_tables(db)
                await db.commit()

            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _create_tables(self, db):
        """Create all required tables"""

        # Device Analytics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS device_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_name TEXT,
            device_type TEXT,
            metric_type TEXT NOT NULL,
            metric_value TEXT,
            numeric_value REAL,
            unit TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(device_id),
            INDEX(metric_type),
            INDEX(timestamp)
        )
        """)

        # Performance Metrics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_category TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            device_id TEXT,
            response_time_ms INTEGER,
            success_rate REAL,
            error_count INTEGER DEFAULT 0,
            metadata TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(metric_name),
            INDEX(metric_category),
            INDEX(timestamp)
        )
        """)

        # Matter Device Bindings Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS matter_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            binding_name TEXT NOT NULL,
            source_device_id TEXT NOT NULL,
            source_node_id INTEGER,
            source_endpoint INTEGER DEFAULT 1,
            target_device_id TEXT NOT NULL,
            target_node_id INTEGER,
            target_endpoint INTEGER DEFAULT 1,
            cluster_id TEXT,
            binding_type TEXT DEFAULT 'matter',
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            INDEX(source_device_id),
            INDEX(target_device_id),
            INDEX(status)
        )
        """)

        # Usage Analytics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS usage_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action_type TEXT NOT NULL,
            entity_id TEXT,
            entity_type TEXT,
            action_details TEXT,
            app_version TEXT,
            platform TEXT,
            session_id TEXT,
            duration_ms INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(action_type),
            INDEX(entity_id),
            INDEX(timestamp)
        )
        """)

        # Reliability Metrics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reliability_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_name TEXT,
            connection_type TEXT,
            uptime_percentage REAL,
            downtime_duration_minutes INTEGER DEFAULT 0,
            last_seen DATETIME,
            connectivity_score REAL,
            error_rate REAL DEFAULT 0.0,
            recovery_time_ms INTEGER,
            status TEXT DEFAULT 'online',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(device_id),
            INDEX(status),
            INDEX(timestamp)
        )
        """)

        # Speed Metrics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS speed_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            device_id TEXT,
            command_type TEXT,
            request_time DATETIME,
            response_time DATETIME,
            latency_ms INTEGER,
            throughput_mbps REAL,
            packet_loss_percentage REAL DEFAULT 0.0,
            network_type TEXT,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(operation_type),
            INDEX(device_id),
            INDEX(timestamp)
        )
        """)

        # Automation Analytics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS automation_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            automation_id TEXT NOT NULL,
            automation_name TEXT,
            trigger_type TEXT,
            trigger_details TEXT,
            execution_time_ms INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            affected_entities TEXT,
            user_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(automation_id),
            INDEX(trigger_type),
            INDEX(timestamp)
        )
        """)

        # Scene Analytics Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS scene_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id TEXT NOT NULL,
            scene_name TEXT,
            activation_method TEXT,
            execution_time_ms INTEGER,
            entities_count INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            user_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(scene_id),
            INDEX(activation_method),
            INDEX(timestamp)
        )
        """)

        # System Health Table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS system_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component TEXT NOT NULL,
            status TEXT NOT NULL,
            cpu_usage REAL,
            memory_usage REAL,
            disk_usage REAL,
            network_usage REAL,
            temperature REAL,
            error_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(component),
            INDEX(status),
            INDEX(timestamp)
        )
        """)

    @asynccontextmanager
    async def get_connection(self):
        """Get async database connection"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def backup_database(self):
        """Create database backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{self.backup_path}/schnell_storage_backup_{timestamp}.db"

            # Ensure backup directory exists
            os.makedirs(self.backup_path, exist_ok=True)

            # Create backup
            async with aiosqlite.connect(self.db_path) as source:
                async with aiosqlite.connect(backup_file) as backup:
                    await source.backup(backup)

            logger.info(f"Database backup created: {backup_file}")

            # Clean old backups (keep last 10)
            await self._cleanup_old_backups()

            return backup_file
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            raise

    async def _cleanup_old_backups(self):
        """Remove old backup files, keep last 10"""
        try:
            backup_files = []
            for file in os.listdir(self.backup_path):
                if file.startswith("schnell_storage_backup_") and file.endswith(".db"):
                    file_path = os.path.join(self.backup_path, file)
                    backup_files.append(
                        (file_path, os.path.getctime(file_path)))

            # Sort by creation time, newest first
            backup_files.sort(key=lambda x: x[1], reverse=True)

            # Remove old backups (keep last 10)
            for file_path, _ in backup_files[10:]:
                os.remove(file_path)
                logger.info(f"Removed old backup: {file_path}")

        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")


# Global database manager instance
db_manager = DatabaseManager()
