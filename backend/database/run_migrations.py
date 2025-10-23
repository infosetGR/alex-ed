#!/usr/bin/env python3
"""
SQLAlchemy-based migration runner for PostgreSQL RDS
"""

import os
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get database URL from environment
database_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')

if not database_uri:
    raise ValueError("Missing SQLALCHEMY_DATABASE_URI in environment variables")

# Create SQLAlchemy engine
engine = sa.create_engine(database_uri)

# Read migration file
migration_file = Path(__file__).parent / 'migrations' / '001_schema.sql'
with open(migration_file) as f:
    sql_content = f.read()

print("🚀 Running database migrations with SQLAlchemy...")
print(f"📍 Database: {database_uri.split('@')[1] if '@' in database_uri else 'Unknown'}")
print("=" * 60)

# Execute the migration in a transaction
with engine.connect() as conn:
    with conn.begin():
        try:
            # Execute the entire migration as one statement
            conn.execute(text(sql_content))
            print("✅ Migration completed successfully!")
            print(f"🏗️  Schema: alex")
            print(f"📊 All tables created in alex schema")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise

print("\n📝 Next steps:")
print("1. Load seed data: uv run seed_data.py")
print("2. Test database operations: uv run test_data_api.py")
