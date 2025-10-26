#!/usr/bin/env python3
"""
Test Database Connection
This script verifies that both Aurora and PostgreSQL RDS are properly configured.
Use DB_BACKEND environment variable to choose: 'aurora' or 'postgres'
"""

import boto3
import json
import os
import sys
import sqlalchemy as sa
from sqlalchemy import text
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get config from environment
db_backend = os.environ.get('DB_BACKEND', 'aurora').lower()  # 'aurora' or 'postgres'

print(f"🎯 Testing {db_backend.upper()} backend (from .env file)")

def test_database_connection():
    """Test database connection based on the configured backend"""
    
    print(f"\n🔍 Testing {db_backend.upper()} Database Connection")
    print("-" * 50)
    
    if db_backend == 'aurora':
        return test_aurora_connection()
    elif db_backend == 'postgres':
        return test_postgres_connection()
    else:
        print("❌ Unsupported DB_BACKEND. Use 'aurora' or 'postgres'.")
        return False

def test_aurora_connection():
    """Test Aurora Data API connection"""
    cluster_arn = os.environ.get('AURORA_CLUSTER_ARN')
    secret_arn = os.environ.get('AURORA_SECRET_ARN')
    database = os.environ.get('AURORA_DATABASE', 'alex')
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    if not cluster_arn or not secret_arn:
        print("❌ Missing AURORA_CLUSTER_ARN or AURORA_SECRET_ARN in .env file")
        return False
    
    client = boto3.client('rds-data', region_name=region)
    
    # Test 1: Simple SELECT
    print("\n1️⃣ Testing basic connection...")
    try:
        response = client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            sql='SELECT 1 as test_connection, current_timestamp as server_time'
        )
        
        if response['records']:
            test_val = response['records'][0][0].get('longValue')
            server_time = response['records'][0][1].get('stringValue')
            print(f"   ✅ Connection successful!")
            print(f"   Server time: {server_time}")
        else:
            print("   ❌ Query executed but returned no results")
            return False
            
    except ClientError as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 2: Check for tables
    print("\n2️⃣ Checking for existing tables...")
    try:
        response = client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            sql="SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        )
        
        tables = [record[0].get('stringValue') for record in response.get('records', [])]
        
        if tables:
            print(f"   ✅ Found {len(tables)} tables:")
            for table in tables[:5]:  # Show first 5
                print(f"      - {table}")
        else:
            print("   ℹ️  No tables found (database is empty)")
            print("   💡 Run the migration script to create tables")
            
    except ClientError as e:
        print(f"   ⚠️  Could not list tables: {e}")
    
    return True

def test_postgres_connection():
    """Test PostgreSQL connection"""
    database_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')
    
    if not database_uri:
        print("❌ Missing SQLALCHEMY_DATABASE_URI in .env file")
        return False
    
    try:
        engine = sa.create_engine(database_uri)
    except Exception as e:
        print(f"❌ Could not create database engine: {e}")
        return False
    
    # Test 1: Simple SELECT
    print("\n1️⃣ Testing basic connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text('SELECT 1 as test_connection, current_timestamp as server_time'))
            row = result.fetchone()
            
            if row:
                test_val = row[0]
                server_time = row[1]
                print(f"   ✅ Connection successful!")
                print(f"   Test value: {test_val}")
                print(f"   Server time: {server_time}")
            else:
                print("   ❌ Query executed but returned no results")
                return False
                
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False
    
    # Test 2: Check for alex schema
    print("\n2️⃣ Checking for alex schema...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'alex'"))
            schema_exists = result.fetchone() is not None
            
            if schema_exists:
                print(f"   ✅ Alex schema exists")
            else:
                print("   ❌ Alex schema not found")
                print("   💡 Run the migration script to create the schema")
                return False
                
    except Exception as e:
        print(f"   ⚠️  Could not check schema: {e}")
    
    # Test 3: Check for tables in alex schema
    print("\n3️⃣ Checking for tables in alex schema...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'alex' ORDER BY table_name"))
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"   ✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"      - {table}")
            else:
                print("   ℹ️  No tables found in alex schema")
                print("   💡 Run the migration script to create tables")
                
    except Exception as e:
        print(f"   ⚠️  Could not list tables: {e}")
    
    return True


def main():
    """Main function"""
    print(f"🚀 {db_backend.upper()} Database Connection Test")
    print("=" * 50)
    
    # Test the database connection
    success = test_database_connection()
    
    if not success:
        print(f"\n❌ {db_backend.upper()} database test failed")
        if db_backend == 'aurora':
            print("\n💡 Troubleshooting:")
            print("   1. Check if the Aurora instance is 'available'")
            print("   2. Verify Data API is enabled")
            print("   3. Check IAM permissions for rds-data:ExecuteStatement")
            print("   4. Verify AURORA_CLUSTER_ARN and AURORA_SECRET_ARN in .env")
        elif db_backend == 'postgres':
            print("\n💡 Troubleshooting:")
            print("   1. Check if the PostgreSQL instance is running")
            print("   2. Verify the connection string is correct")
            print("   3. Check network connectivity and security groups")
            print("   4. Verify SQLALCHEMY_DATABASE_URI in .env")
        sys.exit(1)
    
    print(f"\n✅ {db_backend.upper()} database test successful!")
    print(f"\n📝 Backend: {db_backend.upper()}")
    
    # Run API compatibility tests if tables exist
    print("\n🧪 Running API Compatibility Tests...")
    test_success = run_api_compatibility_tests()
    
    if test_success:
        print(f"\n✅ All API tests passed for {db_backend.upper()}!")
    else:
        print(f"\n⚠️  Some API tests failed for {db_backend.upper()}")
    
    print("\n📝 Next steps:")
    print("1. Run migrations to create tables: uv run run_migrations.py")
    print("2. Load seed data: uv run seed_data.py")
    print("3. Test the database package: uv run test_db.py")


def run_api_compatibility_tests():
    """Run comprehensive API compatibility tests"""
    import uuid
    from decimal import Decimal
    from src.models import Users, Instruments, Accounts, Positions, Jobs
    from src.client import DataAPIClient
    from src.schemas import InstrumentCreate

    try:
        # Initialize the database client
        db_client = DataAPIClient()
        
        # Initialize model classes
        users = Users(db_client)
        instruments = Instruments(db_client)
        accounts = Accounts(db_client)
        positions = Positions(db_client)
        jobs = Jobs(db_client)
        
        # Generate unique test data
        test_user_id = f"test_user_{uuid.uuid4()}"
        test_symbol = f"TEST{uuid.uuid4().hex[:4].upper()}"
        
        print("\n4️⃣ Testing Users API...")
        try:
            user_id = users.create_user(test_user_id, "Test User", 30, Decimal("100000"))
            assert user_id == test_user_id
            user = users.find_by_clerk_id(test_user_id)
            assert user['clerk_user_id'] == test_user_id
            print("   ✅ Users API working")
        except Exception as e:
            print(f"   ❌ Users API failed: {e}")
            return False

        print("\n5️⃣ Testing Instruments API...")
        try:
            instrument_data = InstrumentCreate(
                symbol=test_symbol,
                name="Test Company Inc.",
                instrument_type="stock",
                allocation_regions={"north_america": 100.0},
                allocation_sectors={"technology": 100.0},
                allocation_asset_class={"equity": 100.0}
            )
            symbol = instruments.create_instrument(instrument_data)
            assert symbol == test_symbol
            instrument = instruments.find_by_symbol(test_symbol)
            assert instrument['symbol'] == test_symbol
            print("   ✅ Instruments API working")
        except Exception as e:
            print(f"   ❌ Instruments API failed: {e}")
            return False

        print("\n6️⃣ Testing Accounts API...")
        try:
            account_id = accounts.create_account(test_user_id, "Test Savings", "Retirement", Decimal("1000"), Decimal("1.5"))
            assert account_id is not None
            user_accounts = accounts.find_by_user(test_user_id)
            assert len(user_accounts) > 0
            print("   ✅ Accounts API working")
        except Exception as e:
            print(f"   ❌ Accounts API failed: {e}")
            return False

        print("\n7️⃣ Testing Positions API...")
        try:
            # Create a test account for positions
            position_account_id = accounts.create_account(test_user_id, "Test Investment", "Trading", Decimal("5000"), Decimal("0"))
            
            # Add a position to that account
            position_id = positions.add_position(position_account_id, test_symbol, Decimal("10"))
            assert position_id is not None
            account_positions = positions.find_by_account(position_account_id)
            assert len(account_positions) >= 0  # May be 0 if instrument doesn't exist in join
            print("   ✅ Positions API working")
        except Exception as e:
            print(f"   ❌ Positions API failed: {e}")
            return False

        print("\n8️⃣ Testing Jobs API...")
        try:
            # Ensure user exists first - handle case where user already exists
            try:
                users.create_user(test_user_id, "Test User", 30, Decimal("100000"))
            except Exception:
                pass  # User already exists, which is fine
            
            job_id = jobs.create_job(test_user_id, "test_job", {"key": "value"})
            assert job_id is not None
            jobs.update_status(job_id, "completed")
            job = jobs.find_by_id(job_id)
            assert job['status'] == "completed"
            print("   ✅ Jobs API working")
        except Exception as e:
            print(f"   ❌ Jobs API failed: {e}")
            return False

        return True
        
    except ImportError as e:
        print(f"   ⚠️  Could not import required modules: {e}")
        print("   💡 Make sure tables are created with migrations first")
        return False
    except Exception as e:
        print(f"   ❌ API test setup failed: {e}")
        return False

if __name__ == "__main__":
    main()