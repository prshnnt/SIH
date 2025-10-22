from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from .db_setup import Base

# -----------------------------
# Main Metadata Table
# -----------------------------
class ArgoFloatMetadata(Base):
    __tablename__ = "argo_float_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wmo = Column(String(10), nullable=False)
    file_path = Column(Text)
    profiler_type = Column(String(10))
    institution = Column(String(50))
    date_update = Column(DateTime)

    # Global attributes
    global_title = Column(Text)
    global_institution = Column(String(100))
    global_source = Column(Text)
    global_history = Column(Text)
    global_references = Column(Text)
    global_comment = Column(Text)
    global_user_manual_version = Column(String(20))
    global_conventions = Column(String(50))

    # Platform information
    platform_number = Column(String(10), nullable=False)
    project_name = Column(Text)
    principal_investigator = Column(String(255))
    platform_type = Column(String(50))
    float_serial_number = Column(String(50))
    firmware_version = Column(String(50))

    # Launch info
    launch_date = Column(DateTime, nullable=False)
    launch_longitude = Column(Float)
    launch_latitude = Column(Float)
    deployment_platform = Column(String(255))
    deployment_cruise_id = Column(String(50))

    # Hardware
    battery_type = Column(String(100))
    battery_packs = Column(Text)
    controller_board_primary = Column(String(100))
    controller_board_serial_primary = Column(String(50))

    # Data management
    data_centre = Column(String(10))
    wmo_instrument_type = Column(String(10))

    # Transmission
    transmission_system = Column(String(15))
    transmission_system_id = Column(String(15))
    transmission_frequency = Column(String(15))

    # Mission dates
    start_date = Column(DateTime)
    start_date_qc = Column(String(1))
    end_mission_date = Column(DateTime)
    end_mission_status = Column(String(50))

    # Metadata timestamps
    extraction_date = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("wmo", "platform_number", "launch_date", name="unique_wmo_platform"),
        CheckConstraint("launch_longitude >= -180 AND launch_longitude <= 180", name="valid_longitude"),
        CheckConstraint("launch_latitude >= -90 AND launch_latitude <= 90", name="valid_latitude"),
    )

    # Relationships
    configs = relationship("ArgoLaunchConfig", cascade="all, delete-orphan", back_populates="float")
    sensors = relationship("ArgoSensor", cascade="all, delete-orphan", back_populates="float")
    positioning_systems = relationship("ArgoPositioningSystem", cascade="all, delete-orphan", back_populates="float")
    transmissions = relationship("ArgoTransmissionSystem", cascade="all, delete-orphan", back_populates="float")


# -----------------------------
# Launch Config Table
# -----------------------------
class ArgoLaunchConfig(Base):
    __tablename__ = "argo_launch_config"

    id = Column(Integer, primary_key=True)
    float_id = Column(Integer, ForeignKey("argo_float_metadata.id", ondelete="CASCADE"), nullable=False)
    parameter_name = Column(String(255), nullable=False)
    parameter_value = Column(Float)
    parameter_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("float_id", "parameter_order", name="unique_float_param_order"),
    )

    float = relationship("ArgoFloatMetadata", back_populates="configs")


# -----------------------------
# Sensors Table
# -----------------------------
class ArgoSensor(Base):
    __tablename__ = "argo_sensors"

    id = Column(Integer, primary_key=True)
    float_id = Column(Integer, ForeignKey("argo_float_metadata.id", ondelete="CASCADE"), nullable=False)
    sensor_type = Column(String(50), nullable=False)
    maker = Column(String(100))
    model = Column(String(100))
    serial_number = Column(String(100))
    sensor_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("float_id", "sensor_order", name="unique_float_sensor_order"),
    )

    float = relationship("ArgoFloatMetadata", back_populates="sensors")


# -----------------------------
# Positioning Systems Table
# -----------------------------
class ArgoPositioningSystem(Base):
    __tablename__ = "argo_positioning_systems"

    id = Column(Integer, primary_key=True)
    float_id = Column(Integer, ForeignKey("argo_float_metadata.id", ondelete="CASCADE"), nullable=False)
    system_name = Column(String(50), nullable=False)
    system_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("float_id", "system_order", name="unique_float_positioning"),
    )

    float = relationship("ArgoFloatMetadata", back_populates="positioning_systems")


# -----------------------------
# Transmission Systems Table
# -----------------------------
class ArgoTransmissionSystem(Base):
    __tablename__ = "argo_transmission_systems"

    id = Column(Integer, primary_key=True)
    float_id = Column(Integer, ForeignKey("argo_float_metadata.id", ondelete="CASCADE"), nullable=False)
    system_name = Column(String(50), nullable=False)
    system_id = Column(String(50))
    frequency = Column(String(50))
    system_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("float_id", "system_order", name="unique_float_transmission"),
    )

    float = relationship("ArgoFloatMetadata", back_populates="transmissions")


if __name__ == "__main__":
    from .db_setup import engine
    Base.metadata.create_all(bind=engine)
    print("✅ All SQLite tables created successfully.")
