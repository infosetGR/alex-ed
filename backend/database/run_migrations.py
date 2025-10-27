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

def get_migration_file_path():
    """Get the appropriate migration file based on the database backend"""
    migrations_dir = Path(__file__).parent / 'migrations'
    
    if db_backend == 'aurora':
        return migrations_dir / '001_schema.sql'
    elif db_backend == 'postgres':
        return migrations_dir / '001_schema_postgres.sql'
    else:
        raise ValueError(f"Unsupported DB_BACKEND: {db_backend}. Use 'aurora' or 'postgres'.")

def read_migration_file():
    """Read and return the content of the appropriate migration file"""
    migration_file = get_migration_file_path()
    
    if not migration_file.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_file}")
    
    with open(migration_file, 'r') as f:
        return f.read()

# Initialize database connection based on backend
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

# Read the migration SQL content
migration_sql = read_migration_file()
migration_file_path = get_migration_file_path()

print(f"📁 Reading migration from: {migration_file_path.name}")
print("🚀 Running database migrations...")
print("=" * 50)

def split_sql_statements(sql_content):
    """Split SQL content into individual statements, handling multi-line statements properly"""
    statements = []
    current_statement = ""
    in_function = False
    function_delimiter = None
    
    for line in sql_content.split('\n'):
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('--'):
            continue
            
        # Check if we're starting a function definition
        if 'CREATE OR REPLACE FUNCTION' in line.upper() or 'CREATE FUNCTION' in line.upper():
            in_function = True
            function_delimiter = '$$'
        
        current_statement += line + '\n'
        
        # Check for end of function
        if in_function and function_delimiter and line.endswith(function_delimiter + ';'):
            in_function = False
            statements.append(current_statement.strip())
            current_statement = ""
            continue
        
        # For regular statements, split on semicolon
        if not in_function and line.endswith(';'):
            statements.append(current_statement.strip())
            current_statement = ""
    
    # Add any remaining statement
    if current_statement.strip():
        statements.append(current_statement.strip())
    
    return [stmt for stmt in statements if stmt.strip()]

statements = split_sql_statements(migration_sql)

success_count = 0
error_count = 0

def execute_statement(stmt):
    """Execute a single SQL statement based on the database backend"""
    if db_backend == 'aurora':
        return client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            sql=stmt
        )
    elif db_backend == 'postgres':
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text(stmt))

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
    first_line = next((l for l in stmt.split('\n') if l.strip()), "")[:60]
    print(f"\n[{i}/{len(statements)}] Creating {stmt_type}...")
    print(f"    {first_line}...")
    
    try:
        execute_statement(stmt)
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
    print(f"📁 Migration file: {migration_file_path.name}")
    print("\n📝 Next steps:")
    print("1. Load seed data: uv run seed_data.py")
    print("2. Test database operations: uv run test_data_api.py")
else:
    print(f"\n⚠️  Some statements failed. Check errors above.")
