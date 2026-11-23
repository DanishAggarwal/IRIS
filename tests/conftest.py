"""Pytest configuration and test database isolation.

Ensures all tests execute strictly against an isolated test database (iris_test_db)
and never pollute the development database (iris_db).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Determine test database URL
dev_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://iris:iris_password@localhost:5433/iris_db",
)
if "iris_test_db" not in dev_url:
    test_url = dev_url.rsplit("/", 1)[0] + "/iris_test_db"
else:
    test_url = dev_url

# Override environment variable so any subsequent imports pick up the test DB
os.environ["DATABASE_URL"] = test_url

from sqlalchemy import create_engine, text
from database import connection
from database.models import Base

# Ensure the database engine and SessionLocal in database.connection bind to iris_test_db
connection.DATABASE_URL = test_url
connection.engine = create_engine(
    test_url,
    echo=False,
    pool_pre_ping=True,
)
connection.SessionLocal.configure(bind=connection.engine)

# Ensure vector extension and tables exist in test db
with connection.engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

Base.metadata.create_all(bind=connection.engine)
