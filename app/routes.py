from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
import logging
from database import db_manager
from models import (
    DeviceAnalytic, PerformanceMetric, MatterBinding, UsageAnalytic,
    ReliabilityMetric, SpeedMetric, AutomationAnalytic, SceneAnalytic,
    SystemHealth, MetricResponse, AnalyticsResponse, DateRangeQuery,
    AggregationQuery
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Device Analytics Endpoints


@router.post("/analytics/device", response_model=MetricResponse)
async def create_device_analytic(analytic: DeviceAnalytic):
    """Create a new device analytic record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO device_analytics 
                (device_id, device_name, device_type, metric_type, metric_value, numeric_value, unit, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analytic.device_id, analytic.device_name, analytic.device_type,
                analytic.metric_type, analytic.metric_value, analytic.numeric_value,
                analytic.unit, analytic.timestamp or datetime.now()
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create device analytic: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/device", response_model=AnalyticsResponse)
async def get_device_analytics(
    device_id: Optional[str] = None,
    metric_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000)
):
    """Get device analytics with filtering"""
    try:
        conditions = []
        params = []

        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)
        if metric_type:
            conditions.append("metric_type = ?")
            params.append(metric_type)
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        where_clause = " WHERE " + \
            " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        async with db_manager.get_connection() as db:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM device_analytics{where_clause}"
            cursor = await db.execute(count_query, params)
            total_count = (await cursor.fetchone())[0]

            # Get data
            data_query = f"""
                SELECT * FROM device_analytics{where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(data_query, params + [page_size, offset])
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            return AnalyticsResponse(
                total_count=total_count,
                data=data,
                page=page,
                page_size=page_size
            )
    except Exception as e:
        logger.error(f"Failed to get device analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Performance Metrics Endpoints


@router.post("/analytics/performance", response_model=MetricResponse)
async def create_performance_metric(metric: PerformanceMetric):
    """Create a new performance metric record"""
    try:
        async with db_manager.get_connection() as db:
            metadata_json = json.dumps(
                metric.metadata) if metric.metadata else None
            cursor = await db.execute("""
                INSERT INTO performance_metrics 
                (metric_name, metric_category, value, unit, device_id, response_time_ms, 
                 success_rate, error_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.metric_name, metric.metric_category, metric.value, metric.unit,
                metric.device_id, metric.response_time_ms, metric.success_rate,
                metric.error_count, metadata_json
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create performance metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/performance", response_model=AnalyticsResponse)
async def get_performance_metrics(
    metric_name: Optional[str] = None,
    metric_category: Optional[str] = None,
    device_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000)
):
    """Get performance metrics with filtering"""
    try:
        conditions = []
        params = []

        if metric_name:
            conditions.append("metric_name = ?")
            params.append(metric_name)
        if metric_category:
            conditions.append("metric_category = ?")
            params.append(metric_category)
        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        where_clause = " WHERE " + \
            " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        async with db_manager.get_connection() as db:
            count_query = f"SELECT COUNT(*) FROM performance_metrics{where_clause}"
            cursor = await db.execute(count_query, params)
            total_count = (await cursor.fetchone())[0]

            data_query = f"""
                SELECT * FROM performance_metrics{where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(data_query, params + [page_size, offset])
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            return AnalyticsResponse(
                total_count=total_count,
                data=data,
                page=page,
                page_size=page_size
            )
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Matter Bindings Endpoints


@router.post("/bindings/matter", response_model=MetricResponse)
async def create_matter_binding(binding: MatterBinding):
    """Create a new Matter binding record"""
    try:
        async with db_manager.get_connection() as db:
            metadata_json = json.dumps(
                binding.metadata) if binding.metadata else None
            cursor = await db.execute("""
                INSERT INTO matter_bindings 
                (binding_name, source_device_id, source_node_id, source_endpoint,
                 target_device_id, target_node_id, target_endpoint, cluster_id,
                 binding_type, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                binding.binding_name, binding.source_device_id, binding.source_node_id,
                binding.source_endpoint, binding.target_device_id, binding.target_node_id,
                binding.target_endpoint, binding.cluster_id, binding.binding_type,
                binding.status, metadata_json
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create Matter binding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bindings/matter", response_model=AnalyticsResponse)
async def get_matter_bindings(
    source_device_id: Optional[str] = None,
    target_device_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000)
):
    """Get Matter bindings with filtering"""
    try:
        conditions = []
        params = []

        if source_device_id:
            conditions.append("source_device_id = ?")
            params.append(source_device_id)
        if target_device_id:
            conditions.append("target_device_id = ?")
            params.append(target_device_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " WHERE " + \
            " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        async with db_manager.get_connection() as db:
            count_query = f"SELECT COUNT(*) FROM matter_bindings{where_clause}"
            cursor = await db.execute(count_query, params)
            total_count = (await cursor.fetchone())[0]

            data_query = f"""
                SELECT * FROM matter_bindings{where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(data_query, params + [page_size, offset])
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            return AnalyticsResponse(
                total_count=total_count,
                data=data,
                page=page,
                page_size=page_size
            )
    except Exception as e:
        logger.error(f"Failed to get Matter bindings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/bindings/matter/{binding_id}")
async def update_matter_binding(binding_id: int, status: str):
    """Update Matter binding status"""
    try:
        async with db_manager.get_connection() as db:
            await db.execute("""
                UPDATE matter_bindings 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, binding_id))
            await db.commit()
            return {"status": "updated", "id": binding_id}
    except Exception as e:
        logger.error(f"Failed to update Matter binding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bindings/matter/{binding_id}")
async def delete_matter_binding(binding_id: int):
    """Delete Matter binding"""
    try:
        async with db_manager.get_connection() as db:
            await db.execute("DELETE FROM matter_bindings WHERE id = ?", (binding_id,))
            await db.commit()
            return {"status": "deleted", "id": binding_id}
    except Exception as e:
        logger.error(f"Failed to delete Matter binding: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Usage Analytics Endpoints


@router.post("/analytics/usage", response_model=MetricResponse)
async def create_usage_analytic(analytic: UsageAnalytic):
    """Create a new usage analytic record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO usage_analytics
                (user_id, action_type, entity_id, entity_type, action_details,
                 app_version, platform, session_id, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analytic.user_id, analytic.action_type, analytic.entity_id,
                analytic.entity_type, analytic.action_details, analytic.app_version,
                analytic.platform, analytic.session_id, analytic.duration_ms
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create usage analytic: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/usage", response_model=AnalyticsResponse)
async def get_usage_analytics(
    user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    platform: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000)
):
    """Get usage analytics with filtering"""
    try:
        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        where_clause = " WHERE " + \
            " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        async with db_manager.get_connection() as db:
            count_query = f"SELECT COUNT(*) FROM usage_analytics{where_clause}"
            cursor = await db.execute(count_query, params)
            total_count = (await cursor.fetchone())[0]

            data_query = f"""
                SELECT * FROM usage_analytics{where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(data_query, params + [page_size, offset])
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            return AnalyticsResponse(
                total_count=total_count,
                data=data,
                page=page,
                page_size=page_size
            )
    except Exception as e:
        logger.error(f"Failed to get usage analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Reliability Metrics Endpoints


@router.post("/analytics/reliability", response_model=MetricResponse)
async def create_reliability_metric(metric: ReliabilityMetric):
    """Create a new reliability metric record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO reliability_metrics
                (device_id, device_name, connection_type, uptime_percentage,
                 downtime_duration_minutes, last_seen, connectivity_score,
                 error_rate, recovery_time_ms, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.device_id, metric.device_name, metric.connection_type,
                metric.uptime_percentage, metric.downtime_duration_minutes,
                metric.last_seen, metric.connectivity_score, metric.error_rate,
                metric.recovery_time_ms, metric.status
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create reliability metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Speed Metrics Endpoints


@router.post("/analytics/speed", response_model=MetricResponse)
async def create_speed_metric(metric: SpeedMetric):
    """Create a new speed metric record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO speed_metrics
                (operation_type, device_id, command_type, request_time, response_time,
                 latency_ms, throughput_mbps, packet_loss_percentage, network_type,
                 success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.operation_type, metric.device_id, metric.command_type,
                metric.request_time, metric.response_time, metric.latency_ms,
                metric.throughput_mbps, metric.packet_loss_percentage,
                metric.network_type, metric.success, metric.error_message
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create speed metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Automation Analytics Endpoints


@router.post("/analytics/automation", response_model=MetricResponse)
async def create_automation_analytic(analytic: AutomationAnalytic):
    """Create a new automation analytic record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO automation_analytics
                (automation_id, automation_name, trigger_type, trigger_details,
                 execution_time_ms, success, error_message, affected_entities, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analytic.automation_id, analytic.automation_name, analytic.trigger_type,
                analytic.trigger_details, analytic.execution_time_ms, analytic.success,
                analytic.error_message, analytic.affected_entities, analytic.user_id
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create automation analytic: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Scene Analytics Endpoints


@router.post("/analytics/scene", response_model=MetricResponse)
async def create_scene_analytic(analytic: SceneAnalytic):
    """Create a new scene analytic record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO scene_analytics
                (scene_id, scene_name, activation_method, execution_time_ms,
                 entities_count, success, error_message, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analytic.scene_id, analytic.scene_name, analytic.activation_method,
                analytic.execution_time_ms, analytic.entities_count, analytic.success,
                analytic.error_message, analytic.user_id
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create scene analytic: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# System Health Endpoints


@router.post("/analytics/system", response_model=MetricResponse)
async def create_system_health(health: SystemHealth):
    """Create a new system health record"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO system_health
                (component, status, cpu_usage, memory_usage, disk_usage,
                 network_usage, temperature, error_count, warning_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                health.component, health.status, health.cpu_usage, health.memory_usage,
                health.disk_usage, health.network_usage, health.temperature,
                health.error_count, health.warning_count
            ))
            await db.commit()
            return MetricResponse(id=cursor.lastrowid, timestamp=datetime.now())
    except Exception as e:
        logger.error(f"Failed to create system health record: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Aggregation and Analytics Endpoints


@router.post("/analytics/aggregate")
async def get_aggregated_data(query: AggregationQuery):
    """Get aggregated analytics data"""
    try:
        table_map = {
            "device": "device_analytics",
            "performance": "performance_metrics",
            "usage": "usage_analytics",
            "reliability": "reliability_metrics",
            "speed": "speed_metrics",
            "automation": "automation_analytics",
            "scene": "scene_analytics",
            "system": "system_health"
        }

        # Determine table and field
        metric_parts = query.metric_name.split(".")
        if len(metric_parts) != 2:
            raise HTTPException(
                status_code=400, detail="Metric name must be in format 'table.field'")

        table_name = table_map.get(metric_parts[0])
        field_name = metric_parts[1]

        if not table_name:
            raise HTTPException(status_code=400, detail="Invalid table name")

        # Build aggregation query
        agg_func = query.aggregation_type.upper()
        if agg_func not in ["AVG", "SUM", "MIN", "MAX", "COUNT"]:
            raise HTTPException(
                status_code=400, detail="Invalid aggregation type")

        # Time bucket for grouping
        time_format = {
            "hour": "%Y-%m-%d %H:00:00",
            "day": "%Y-%m-%d",
            "week": "%Y-W%W",
            "month": "%Y-%m"
        }.get(query.time_bucket, "%Y-%m-%d %H:00:00")

        conditions = []
        params = []

        if query.start_date:
            conditions.append("timestamp >= ?")
            params.append(query.start_date)
        if query.end_date:
            conditions.append("timestamp <= ?")
            params.append(query.end_date)

        where_clause = " WHERE " + \
            " AND ".join(conditions) if conditions else ""

        group_by_clause = f"strftime('{time_format}', timestamp)"
        if query.group_by:
            group_by_clause += f", {query.group_by}"

        sql_query = f"""
            SELECT
                {group_by_clause} as time_bucket,
                {agg_func}({field_name}) as value
                {f", {query.group_by}" if query.group_by else ""}
            FROM {table_name}
            {where_clause}
            GROUP BY {group_by_clause}
            ORDER BY time_bucket
        """

        async with db_manager.get_connection() as db:
            cursor = await db.execute(sql_query, params)
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            return {
                "metric_name": query.metric_name,
                "aggregation_type": query.aggregation_type,
                "time_bucket": query.time_bucket,
                "data": data
            }
    except Exception as e:
        logger.error(f"Failed to get aggregated data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Utility Endpoints


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM device_analytics")
            total_records = (await cursor.fetchone())[0]

        return {
            "status": "healthy",
            "database_status": "connected",
            "uptime_seconds": 0,  # You can implement actual uptime tracking
            "version": "1.0.0",
            "total_records": total_records
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database_status": "disconnected",
            "error": str(e)
        }


@router.post("/backup")
async def create_backup():
    """Create database backup"""
    try:
        backup_file = await db_manager.backup_database()
        return {"status": "success", "backup_file": backup_file}
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_database_stats():
    """Get database statistics"""
    try:
        stats = {}
        tables = [
            "device_analytics", "performance_metrics", "matter_bindings",
            "usage_analytics", "reliability_metrics", "speed_metrics",
            "automation_analytics", "scene_analytics", "system_health"
        ]

        async with db_manager.get_connection() as db:
            for table in tables:
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                count = (await cursor.fetchone())[0]
                stats[table] = count

        return {"table_counts": stats, "total_records": sum(stats.values())}
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/data/{table_name}")
async def clear_table_data(table_name: str, confirm: bool = Query(False)):
    """Clear all data from a specific table (use with caution)"""
    if not confirm:
        raise HTTPException(
            status_code=400, detail="Must set confirm=true to clear data")

    allowed_tables = [
        "device_analytics", "performance_metrics", "matter_bindings",
        "usage_analytics", "reliability_metrics", "speed_metrics",
        "automation_analytics", "scene_analytics", "system_health"
    ]

    if table_name not in allowed_tables:
        raise HTTPException(status_code=400, detail="Invalid table name")

    try:
        async with db_manager.get_connection() as db:
            await db.execute(f"DELETE FROM {table_name}")
            await db.commit()

        return {"status": "success", "message": f"All data cleared from {table_name}"}
    except Exception as e:
        logger.error(f"Failed to clear table {table_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
