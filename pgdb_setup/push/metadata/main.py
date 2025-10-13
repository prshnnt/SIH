from commit import load_parquet_to_postgres
import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
if __name__ == "__main__":
    # Replace with your parquet file path
    PARQUET_FILE = "data/allmetadata.parquet"
    if DATABASE_URL:
        print("Using DATABASE_URL from environment")
        load_parquet_to_postgres(PARQUET_FILE ,URL=DATABASE_URL)
    else:
        print("Using DB_CONFIG from environment")
        load_parquet_to_postgres(PARQUET_FILE)