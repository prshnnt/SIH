pgdb_setup/
│
├── fetch/
│   ├── __init__.py
│   └── fetch_data.py         # Fetches external data → saves to JSON/CSV
│
├── push/
│   ├── __init__.py
│   └── push_data.py          # Reads files from fetch/, processes → inserts into DB
│
├── testdb/
│   ├── __init__.py
│   ├── db_setup.py           # Connection + Session management
│   ├── models.py             # SQLAlchemy models (tables)
│   ├── crud.py               # Helper DB operations
│   └── database.sqlite3
│
└── data/
    └── fetched_users.json    # (example fetched data)
