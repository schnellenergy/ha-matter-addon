from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class MetricType(str, Enum):
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    USAGE = "usage"
    SPEED = "speed"
    DEVICE = "device"
    AUTOMATION = "automation"
    SCENE = "scene"
    SYSTEM = "system"

class DeviceAnalytic(BaseModel):
    device_id: str = Field(..., description="Unique device identifier")
    device_name: Optional[str] = Field(None, description="Human readable device name")
    device_type: Optional[str] = Field(None, description="Type of device (light, switch, sensor, etc.)")
    metric_type: str = Field(..., description="Type of metric being recorded")
    metric_value: Optional[str] = Field(None, description="String value of the metric")
    numeric_value: Optional[float] = Field(None, description="Numeric value of the metric")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    timestamp: Optional[datetime] = Field(None, description="When the metric was recorded")

class PerformanceMetric(BaseModel):
    metric_name: str = Field(..., description="Name of the performance metric")
    metric_category: str = Field(..., description="Category of the metric")
    value: float = Field(..., description="Numeric value of the metric")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    device_id: Optional[str] = Field(None, description="Associated device ID")
    response_time_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    success_rate: Optional[float] = Field(None, description="Success rate percentage")
    error_count: Optional[int] = Field(0, description="Number of errors")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class MatterBinding(BaseModel):
    binding_name: str = Field(..., description="Name of the binding")
    source_device_id: str = Field(..., description="Source device identifier")
    source_node_id: Optional[int] = Field(None, description="Source Matter node ID")
    source_endpoint: Optional[int] = Field(1, description="Source endpoint")
    target_device_id: str = Field(..., description="Target device identifier")
    target_node_id: Optional[int] = Field(None, description="Target Matter node ID")
    target_endpoint: Optional[int] = Field(1, description="Target endpoint")
    cluster_id: Optional[str] = Field(None, description="Matter cluster ID")
    binding_type: Optional[str] = Field("matter", description="Type of binding")
    status: Optional[str] = Field("active", description="Binding status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class UsageAnalytic(BaseModel):
    user_id: Optional[str] = Field(None, description="User identifier")
    action_type: str = Field(..., description="Type of action performed")
    entity_id: Optional[str] = Field(None, description="Entity that was acted upon")
    entity_type: Optional[str] = Field(None, description="Type of entity")
    action_details: Optional[str] = Field(None, description="Additional action details")
    app_version: Optional[str] = Field(None, description="App version")
    platform: Optional[str] = Field(None, description="Platform (iOS, Android, Web)")
    session_id: Optional[str] = Field(None, description="Session identifier")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds")

class ReliabilityMetric(BaseModel):
    device_id: str = Field(..., description="Device identifier")
    device_name: Optional[str] = Field(None, description="Device name")
    connection_type: Optional[str] = Field(None, description="Connection type (WiFi, Zigbee, Matter, etc.)")
    uptime_percentage: Optional[float] = Field(None, description="Uptime percentage")
    downtime_duration_minutes: Optional[int] = Field(0, description="Downtime in minutes")
    last_seen: Optional[datetime] = Field(None, description="Last seen timestamp")
    connectivity_score: Optional[float] = Field(None, description="Overall connectivity score")
    error_rate: Optional[float] = Field(0.0, description="Error rate percentage")
    recovery_time_ms: Optional[int] = Field(None, description="Recovery time in milliseconds")
    status: Optional[str] = Field("online", description="Current status")

class SpeedMetric(BaseModel):
    operation_type: str = Field(..., description="Type of operation")
    device_id: Optional[str] = Field(None, description="Device identifier")
    command_type: Optional[str] = Field(None, description="Type of command")
    request_time: Optional[datetime] = Field(None, description="Request timestamp")
    response_time: Optional[datetime] = Field(None, description="Response timestamp")
    latency_ms: Optional[int] = Field(None, description="Latency in milliseconds")
    throughput_mbps: Optional[float] = Field(None, description="Throughput in Mbps")
    packet_loss_percentage: Optional[float] = Field(0.0, description="Packet loss percentage")
    network_type: Optional[str] = Field(None, description="Network type")
    success: Optional[bool] = Field(True, description="Operation success")
    error_message: Optional[str] = Field(None, description="Error message if failed")

class AutomationAnalytic(BaseModel):
    automation_id: str = Field(..., description="Automation identifier")
    automation_name: Optional[str] = Field(None, description="Automation name")
    trigger_type: Optional[str] = Field(None, description="Type of trigger")
    trigger_details: Optional[str] = Field(None, description="Trigger details")
    execution_time_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    success: Optional[bool] = Field(True, description="Execution success")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    affected_entities: Optional[str] = Field(None, description="Affected entities (JSON)")
    user_id: Optional[str] = Field(None, description="User who triggered")

class SceneAnalytic(BaseModel):
    scene_id: str = Field(..., description="Scene identifier")
    scene_name: Optional[str] = Field(None, description="Scene name")
    activation_method: Optional[str] = Field(None, description="How scene was activated")
    execution_time_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    entities_count: Optional[int] = Field(None, description="Number of entities in scene")
    success: Optional[bool] = Field(True, description="Execution success")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    user_id: Optional[str] = Field(None, description="User who activated")

class SystemHealth(BaseModel):
    component: str = Field(..., description="System component")
    status: str = Field(..., description="Component status")
    cpu_usage: Optional[float] = Field(None, description="CPU usage percentage")
    memory_usage: Optional[float] = Field(None, description="Memory usage percentage")
    disk_usage: Optional[float] = Field(None, description="Disk usage percentage")
    network_usage: Optional[float] = Field(None, description="Network usage percentage")
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")
    error_count: Optional[int] = Field(0, description="Error count")
    warning_count: Optional[int] = Field(0, description="Warning count")

# Response models
class MetricResponse(BaseModel):
    id: int
    timestamp: datetime
    status: str = "success"

class AnalyticsResponse(BaseModel):
    total_count: int
    data: List[Dict[str, Any]]
    page: Optional[int] = None
    page_size: Optional[int] = None

class HealthResponse(BaseModel):
    status: str
    database_status: str
    uptime_seconds: int
    version: str = "1.0.0"
    total_records: int

# Query models
class DateRangeQuery(BaseModel):
    start_date: Optional[datetime] = Field(None, description="Start date for filtering")
    end_date: Optional[datetime] = Field(None, description="End date for filtering")
    device_id: Optional[str] = Field(None, description="Filter by device ID")
    metric_type: Optional[str] = Field(None, description="Filter by metric type")
    page: Optional[int] = Field(1, description="Page number")
    page_size: Optional[int] = Field(100, description="Page size")

class AggregationQuery(BaseModel):
    metric_name: str = Field(..., description="Metric to aggregate")
    aggregation_type: str = Field("avg", description="Type of aggregation (avg, sum, min, max, count)")
    group_by: Optional[str] = Field(None, description="Group by field")
    time_bucket: Optional[str] = Field("hour", description="Time bucket (hour, day, week, month)")
    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")
