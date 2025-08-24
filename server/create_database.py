import pandas as pd
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLAlchemy setup
DATABASE_URL = "sqlite:///sih_ps.db"
engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

# ORM Model
class SIHPS(Base):
    __tablename__ = "sih_ps"
    Statement_id = Column(String, primary_key=True,unique=True, nullable=False)
    Title = Column(Text)
    Technology_Bucket = Column(Text)
    Department = Column(Text)
    Organisation = Column(Text)
    Description = Column(Text)

# Create table
Base.metadata.create_all(engine)

# Read Excel data
df = pd.read_excel("./data/sih_ps_2024_cleaned.xlsx", sheet_name="sih_ps", engine="openpyxl")

# Insert data
Session = sessionmaker(bind=engine)
session = Session()

session.bulk_insert_mappings(SIHPS, df.to_dict(orient="records"))
session.commit()
session.close()