from sqlalchemy.orm import Session
from .models import ArgoFloatMetadata as ORMFloat

def add_argo_float(db: Session, float_data):
    """Insert Pydantic validated float data into DB."""
    float_db = ORMFloat(
        wmo=float_data.wmo,
        platform_number=float_data.platform_number,
        launch_date=float_data.launch_date,
        launch_longitude=float_data.launch_longitude,
        launch_latitude=float_data.launch_latitude,
        institution=float_data.institution,
        # Map other fields similarly...
    )
    db.add(float_db)
    db.commit()
    db.refresh(float_db)
    return float_db
