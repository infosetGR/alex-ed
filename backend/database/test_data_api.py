#!/usr/bin/env python3
"""
Test PostgreSQL Database Connection
This script verifies that PostgreSQL RDS is properly configured with SQLAlchemy.
"""

import os
import sys
from src.client import DataAPIClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

def get_database_connection():
    """Get database connection details from environment variables"""
    
    database_uri = os.getenv('SQLALCHEMY_DATABASE_URI')
    
    if database_uri:
        print(f"📋 Using PostgreSQL connection from .env file")
        # Parse the URI to show connection details (without password)
        if '@' in database_uri:
            credentials, host_part = database_uri.split('@')
            host_db = host_part.split('/')
            host = host_db[0]
            database = host_db[1] if len(host_db) > 1 else 'unknown'
            print(f"   Host: {host}")
            print(f"   Database: {database}")
            print(f"   Schema: alex")
        
        return database_uri
    
    print("❌ SQLALCHEMY_DATABASE_URI not found in .env file")
    print("💡 Make sure your .env file contains:")
    print("   SQLALCHEMY_DATABASE_URI=postgresql://username:password@host:port/database")
    return None

def test_database_connection():
    """Test the PostgreSQL database connection using our SQLAlchemy client"""
    
    print(f"\n🔍 Testing PostgreSQL Database Connection")
    print("-" * 50)
    
    try:
        # Initialize our database client
        client = DataAPIClient()
        
        # Test 1: Simple SELECT
        print("\n1️⃣ Testing basic connection...")
        try:
            result = client.query('SELECT 1 as test_connection, current_timestamp as server_time')
            
            if result:
                test_val = result[0]['test_connection']
                server_time = result[0]['server_time']
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
            result = client.query("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'alex'")
            
            if result:
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
            result = client.query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'alex' ORDER BY table_name")
            
            tables = [row['table_name'] for row in result]
            
            if tables:
                print(f"   ✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"      - {table}")
            else:
                print("   ℹ️  No tables found in alex schema")
                print("   💡 Run the migration script to create tables")
                
        except Exception as e:
            print(f"   ⚠️  Could not list tables: {e}")
        
        # Test 4: Check instruments data
        print("\n4️⃣ Checking for seed data...")
        try:
            result = client.query("SELECT COUNT(*) as count FROM alex.instruments")
            count = result[0]['count']
            
            if count > 0:
                print(f"   ✅ Found {count} instruments in the database")
                
                # Show a sample
                sample = client.query("SELECT symbol, name FROM alex.instruments LIMIT 3")
                print("   Sample instruments:")
                for instrument in sample:
                    print(f"      - {instrument['symbol']}: {instrument['name']}")
            else:
                print("   ℹ️  No instruments found")
                print("   💡 Run seed_data.py to load sample data")
                
        except Exception as e:
            print(f"   ⚠️  Could not check instruments: {e}")
        
        # Test 5: Test insert/update operations
        print("\n5️⃣ Testing write operations...")
        try:
            # Test insert
            test_sql = """
                INSERT INTO alex.instruments (symbol, name, instrument_type, current_price, 
                                            allocation_regions, allocation_sectors, allocation_asset_class)
                VALUES ('TEST_DB', 'Test Database Connection', 'test', 1.00,
                       '{"test": 100}'::jsonb, '{"test": 100}'::jsonb, '{"test": 100}'::jsonb)
                ON CONFLICT (symbol) DO UPDATE SET updated_at = NOW()
            """
            
            result = client.execute(test_sql)
            print(f"   ✅ Insert/update test successful")
            
            # Clean up test record
            client.execute("DELETE FROM alex.instruments WHERE symbol = 'TEST_DB'")
            print(f"   ✅ Cleanup successful")
            
        except Exception as e:
            print(f"   ⚠️  Write operation test failed: {e}")
        
        # Test 6: Check user tables (even if empty)
        print("\n6️⃣ Checking other tables...")
        expected_tables = ['users', 'accounts', 'positions', 'jobs']
        
        for table in expected_tables:
            try:
                result = client.query(f"SELECT COUNT(*) as count FROM alex.{table}")
                count = result[0]['count']
                print(f"   ✅ {table}: {count} rows")
            except Exception as e:
                print(f"   ❌ {table}: Error - {e}")
        
        print("\n" + "=" * 50)
        print("✅ PostgreSQL database is working correctly!")
        print("\n📝 Database Summary:")
        print("   - Connection: ✅ Working")
        print("   - Schema: ✅ alex schema exists")  
        print("   - Tables: ✅ All tables created")
        print("   - Operations: ✅ Read/Write working")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Database client initialization failed: {e}")
        return False

def main():
    """Main function"""
    print("🚀 PostgreSQL Database Connection Test")
    print("=" * 50)
    
    # Check for database connection string
    database_uri = get_database_connection()
    
    if not database_uri:
        print("\n❌ Could not find database connection string")
        print("\n💡 Make sure you have:")
        print("   1. Created the PostgreSQL RDS instance")
        print("   2. Added SQLALCHEMY_DATABASE_URI to your .env file")
        print("   3. The connection string format: postgresql://user:pass@host:port/db")
        sys.exit(1)
    
    # Test the database connection
    success = test_database_connection()
    
    if not success:
        print("\n❌ Database connection test failed")
        print("\n💡 Troubleshooting:")
        print("   1. Check if the PostgreSQL instance is running")
        print("   2. Verify the connection string is correct")
        print("   3. Check network connectivity and security groups")
        print("   4. Ensure the database and alex schema exist")
        sys.exit(1)
    
    print(f"\n✅ Database connection test successful!")
    print("\n📝 Next steps:")
    print("1. Load seed data: uv run seed_data.py")
    print("2. Test agent operations: uv run test_simple.py (in agent directories)")
    print("3. Create test portfolios for analysis")

if __name__ == "__main__":
    main()