from pydantic import BaseModel, EmailStr, Field

class UserSchema(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    username: str | None = None

    class Config:
        orm_mode = True


from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional , List, Any

# according to schema of database

# argo_float_metadata
class ArgoFloatMetadata(BaseModel):
    id: Optional[int]
    wmo: str = Field(..., max_length=7, min_length=7)
    file_path: Optional[str]
    profiler_type: Optional[str]
    institution: Optional[str]
    date_update: Optional[datetime]

    # Global attributes
    global_title: Optional[str]
    global_institution: Optional[str]
    global_source: Optional[str]
    global_history: Optional[str]
    global_references: Optional[str]
    global_comment: Optional[str]
    global_user_manual_version: Optional[str]
    global_conventions: Optional[str]

    # Platform information
    platform_number: str = Field(..., max_length=7, min_length=7)
    project_name: Optional[str]
    principal_investigator: Optional[str]
    platform_type: Optional[str]
    float_serial_number: Optional[str]
    firmware_version: Optional[str]

    # Launch information
    launch_date: datetime
    launch_longitude: Optional[float] = Field(ge=-180, le=180)
    launch_latitude: Optional[float] = Field(ge=-90, le=90)
    deployment_platform: Optional[str]
    deployment_cruise_id: Optional[str]

    # Hardware info
    battery_type: Optional[str]
    battery_packs: Optional[str]
    controller_board_primary: Optional[str]
    controller_board_serial_primary: Optional[str]

    # Data management
    data_centre: Optional[str]
    wmo_instrument_type: Optional[str]

    # Mission dates
    start_date: Optional[datetime]
    start_date_qc: Optional[str]
    end_mission_date: Optional[datetime]
    end_mission_status: Optional[str]

    # Metadata
    extraction_date: Optional[datetime] = Field(default_factory=datetime.utcnow)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# argo_launch_config
class ArgoLaunchConfig(BaseModel):
    id: Optional[int]
    float_id: int
    float_launch_date: datetime
    parameter_name: str
    parameter_value: Optional[float]
    parameter_order: int
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# argo_config_history
class ArgoConfigHistory(BaseModel):
    id: Optional[int]
    float_id: int
    float_launch_date: datetime
    config_set: int = 1
    parameter_name: str
    parameter_value: Optional[float]
    parameter_order: int
    effective_date: Optional[datetime]
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# argo_sensors
class ArgoSensor(BaseModel):
    id: Optional[int]
    float_id: int
    float_launch_date: datetime
    sensor_type: str
    maker: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    sensor_order: int
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# argo_positioning_systems
class ArgoPositioningSystem(BaseModel):
    id: Optional[int]
    float_id: int
    float_launch_date: datetime
    system_name: str
    system_order: int
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# argo_transmission_systems
class ArgoTransmissionSystem(BaseModel):
    id: Optional[int]
    float_id: int
    float_launch_date: datetime
    system_name: str
    system_id: Optional[str]
    frequency: Optional[str]
    system_order: int
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


# (Optional) View Model – v_argo_float_complete
# This model can be used for API responses combining all float data:

class ArgoFloatComplete(BaseModel):
    id: int
    wmo: str
    platform_number: str
    launch_date: datetime
    computed_longitude: Optional[float]
    computed_latitude: Optional[float]
    sensor_details: Optional[List[dict]]
    positioning_systems: Optional[List[str]]
    transmission_systems: Optional[List[str]]