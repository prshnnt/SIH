@echo off
cd ../pgdb_setup/fetch_metadata/data
copy allmetadata.parquet ..\allmetadata.parquet
cd ..
move allmetadata.parquet ..\..\server\data\allmetadata.parquet