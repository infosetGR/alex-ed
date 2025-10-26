#!/usr/bin/env python3
"""
Migration runner supporting both Aurora and PostgreSQL RDS.
Use DB_BACKEND environment variable to choose: 'aurora' or 'postgres'
"""

import os
import boto3
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get config from environment
db_backend = os.environ.get('DB_BACKEND', 'aurora').lower()  # 'aurora' or 'postgres'

print(f"🎯 Using {db_backend.upper()} backend")

if db_backend == 'aurora':
    cluster_arn = os.environ.get('AURORA_CLUSTER_ARN')
    secret_arn = os.environ.get('AURORA_SECRET_ARN')
    database = os.environ.get('AURORA_DATABASE', 'alex')
    region = os.environ.get('AWS_REGION', 'us-east-1')

    if not cluster_arn or not secret_arn:
        raise ValueError("Missing AURORA_CLUSTER_ARN or AURORA_SECRET_ARN in environment variables")

    client = boto3.client('rds-data', region_name=region)

elif db_backend == 'postgres':
    database_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')

    if not database_uri:
        raise ValueError("Missing SQLALCHEMY_DATABASE_URI in environment variables")

    engine = sa.create_engine(database_uri)
else:
    raise ValueError("Unsupported DB_BACKEND. Use 'aurora' or 'postgres'.")

# Define statements in order (since splitting is complex)
statements = [
    # Extension/Schema setup
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' if db_backend == 'aurora' else 'CREATE SCHEMA IF NOT EXISTS alex',
    
    # Tables with backend-specific adaptations
    f"""CREATE TABLE IF NOT EXISTS {'alex.' if db_backend == 'postgres' else ''}users (
        clerk_user_id VARCHAR(255) PRIMARY KEY,
        display_name VARCHAR(255),
        years_until_retirement INTEGER,
        target_retirement_income DECIMAL(12,2),
        asset_class_targets JSONB DEFAULT '{{"equity": 70, "fixed_income": 30}}',
        region_targets JSONB DEFAULT '{{"north_america": 50, "international": 50}}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    
    f"""CREATE TABLE IF NOT EXISTS {'alex.' if db_backend == 'postgres' else ''}instruments (
        symbol VARCHAR(20) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        instrument_type VARCHAR(50),
        current_price DECIMAL(12,4),
        allocation_regions JSONB DEFAULT '{{}}',
        allocation_sectors JSONB DEFAULT '{{}}',
        allocation_asset_class JSONB DEFAULT '{{}}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    
    f"""CREATE TABLE IF NOT EXISTS {'alex.' if db_backend == 'postgres' else ''}accounts (
        id UUID PRIMARY KEY DEFAULT {'gen_random_uuid()' if db_backend == 'postgres' else 'uuid_generate_v4()'},
        clerk_user_id VARCHAR(255) REFERENCES {'alex.' if db_backend == 'postgres' else ''}users(clerk_user_id) ON DELETE CASCADE,
        account_name VARCHAR(255) NOT NULL,
        account_purpose TEXT,
        cash_balance DECIMAL(12,2) DEFAULT 0,
        cash_interest DECIMAL(5,4) DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    
    f"""CREATE TABLE IF NOT EXISTS {'alex.' if db_backend == 'postgres' else ''}positions (
        id UUID PRIMARY KEY DEFAULT {'gen_random_uuid()' if db_backend == 'postgres' else 'uuid_generate_v4()'},
        account_id UUID REFERENCES {'alex.' if db_backend == 'postgres' else ''}accounts(id) ON DELETE CASCADE,
        symbol VARCHAR(20) REFERENCES {'alex.' if db_backend == 'postgres' else ''}instruments(symbol),
        quantity DECIMAL(20,8) NOT NULL,
        as_of_date DATE DEFAULT CURRENT_DATE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(account_id, symbol)
    )""",
    
    f"""CREATE TABLE IF NOT EXISTS {'alex.' if db_backend == 'postgres' else ''}jobs (
        id UUID PRIMARY KEY DEFAULT {'gen_random_uuid()' if db_backend == 'postgres' else 'uuid_generate_v4()'},
        clerk_user_id VARCHAR(255) REFERENCES {'alex.' if db_backend == 'postgres' else ''}users(clerk_user_id) ON DELETE CASCADE,
        job_type VARCHAR(50) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        request_payload JSONB,
        report_payload JSONB,
        charts_payload JSONB,
        retirement_payload JSONB,
        summary_payload JSONB,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    
    # Indexes
    f'CREATE INDEX IF NOT EXISTS idx_accounts_user ON {"alex." if db_backend == "postgres" else ""}accounts(clerk_user_id)',
    f'CREATE INDEX IF NOT EXISTS idx_positions_account ON {"alex." if db_backend == "postgres" else ""}positions(account_id)',
    f'CREATE INDEX IF NOT EXISTS idx_positions_symbol ON {"alex." if db_backend == "postgres" else ""}positions(symbol)',
    f'CREATE INDEX IF NOT EXISTS idx_jobs_user ON {"alex." if db_backend == "postgres" else ""}jobs(clerk_user_id)',
    f'CREATE INDEX IF NOT EXISTS idx_jobs_status ON {"alex." if db_backend == "postgres" else ""}jobs(status)',
    
    # Function for timestamps
    """CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    
    # Triggers
    f"""CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON {"alex." if db_backend == "postgres" else ""}users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    
    f"""CREATE TRIGGER update_instruments_updated_at BEFORE UPDATE ON {"alex." if db_backend == "postgres" else ""}instruments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    
    f"""CREATE TRIGGER update_accounts_updated_at BEFORE UPDATE ON {"alex." if db_backend == "postgres" else ""}accounts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    
    f"""CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON {"alex." if db_backend == "postgres" else ""}positions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    
    f"""CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON {"alex." if db_backend == "postgres" else ""}jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
]

print("🚀 Running database migrations...")
print("=" * 50)

success_count = 0
error_count = 0

for i, stmt in enumerate(statements, 1):
    # Get a description of what we're creating
    stmt_type = "statement"
    if "CREATE TABLE" in stmt.upper():
        stmt_type = "table"
    elif "CREATE INDEX" in stmt.upper():
        stmt_type = "index"
    elif "CREATE TRIGGER" in stmt.upper():
        stmt_type = "trigger"
    elif "CREATE FUNCTION" in stmt.upper():
        stmt_type = "function"
    elif "CREATE EXTENSION" in stmt.upper():
        stmt_type = "extension"
    elif "CREATE SCHEMA" in stmt.upper():
        stmt_type = "schema"
    
    # First non-empty line for display
    first_line = next(l for l in stmt.split('\n') if l.strip())[:60]
    print(f"\n[{i}/{len(statements)}] Creating {stmt_type}...")
    print(f"    {first_line}...")
    
    try:
        if db_backend == 'aurora':
            response = client.execute_statement(
                resourceArn=cluster_arn,
                secretArn=secret_arn,
                database=database,
                sql=stmt
            )
        elif db_backend == 'postgres':
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text(stmt))
        
        print(f"    ✅ Success")
        success_count += 1
        
    except Exception as e:
        error_msg = str(e)
        if 'already exists' in error_msg.lower():
            print(f"    ⚠️  Already exists (skipping)")
            success_count += 1
        else:
            print(f"    ❌ Error: {error_msg[:100]}")
            error_count += 1

print("\n" + "=" * 50)
print(f"Migration complete: {success_count} successful, {error_count} errors")

if error_count == 0:
    print("\n✅ All migrations completed successfully!")
    print(f"\n📝 Backend: {db_backend.upper()}")
    print("\n📝 Next steps:")
    print("1. Load seed data: uv run seed_data.py")
    print("2. Test database operations: uv run test_data_api.py")
else:
    print(f"\n⚠️  Some statements failed. Check errors above.")
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
