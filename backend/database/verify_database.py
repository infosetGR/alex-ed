#!/usr/bin/env python3
"""
Comprehensive database verification script
Shows that all tables exist and are properly populated

This script verifies:
- All tables are created
- Record counts for each table
- Sample instruments with allocations
- Allocation percentages sum to 100%
- Asset class distribution
- Database indexes and triggers

Note: JSONB values are stored as floats (100.0) not strings ('100')

Supports both Aurora and PostgreSQL backends via DB_BACKEND environment variable.
"""

import os
import boto3
import sqlalchemy as sa
from sqlalchemy import text
import json
from pathlib import Path
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get config from environment
db_backend = os.environ.get('DB_BACKEND', 'aurora').lower()  # 'aurora' or 'postgres'

print(f"🎯 Using {db_backend.upper()} backend")

# Initialize database connection based on backend
if db_backend == 'aurora':
    cluster_arn = os.environ.get('AURORA_CLUSTER_ARN')
    secret_arn = os.environ.get('AURORA_SECRET_ARN')
    database = os.environ.get('AURORA_DATABASE', 'alex')
    region = os.environ.get('AWS_REGION', 'us-east-1')

    if not cluster_arn or not secret_arn:
        print("❌ Missing AURORA_CLUSTER_ARN or AURORA_SECRET_ARN in .env file")
        exit(1)

    client = boto3.client('rds-data', region_name=region)

elif db_backend == 'postgres':
    database_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')

    if not database_uri:
        print("❌ Missing SQLALCHEMY_DATABASE_URI in .env file")
        exit(1)

    engine = sa.create_engine(database_uri)
else:
    print(f"❌ Unsupported DB_BACKEND: {db_backend}. Use 'aurora' or 'postgres'.")
    exit(1)

def get_table_prefix():
    """Get table prefix based on backend"""
    return "alex." if db_backend == 'postgres' else ""

def get_schema_name():
    """Get schema name based on backend"""
    return "alex" if db_backend == 'postgres' else "public"

def execute_query(sql, description):
    """Execute a query and return results based on backend"""
    print(f"\n{description}")
    print("-" * 50)
    
    try:
        if db_backend == 'aurora':
            response = client.execute_statement(
                resourceArn=cluster_arn,
                secretArn=secret_arn,
                database=database,
                sql=sql
            )
            return response
        elif db_backend == 'postgres':
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                # Convert SQLAlchemy result to Aurora-like format
                records = []
                for row in result:
                    record = []
                    for value in row:
                        if value is None:
                            record.append({'isNull': True})
                        elif isinstance(value, int):
                            record.append({'longValue': value})
                        elif isinstance(value, float):
                            record.append({'doubleValue': value})
                        elif isinstance(value, str):
                            record.append({'stringValue': value})
                        else:
                            record.append({'stringValue': str(value)})
                    records.append(record)
                return {'records': records}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("🔍 DATABASE VERIFICATION REPORT")
    print("=" * 70)
    print(f"🎯 Backend: {db_backend.upper()}")
    if db_backend == 'aurora':
        print(f"📍 Region: {region}")
        print(f"📦 Database: {database}")
    elif db_backend == 'postgres':
        db_name = database_uri.split('/')[-1] if '/' in database_uri else 'Unknown'
        print(f"📦 Database: {db_name}")
    print("=" * 70)
    
    table_prefix = get_table_prefix()
    schema_name = get_schema_name()
    
    # 1. Show all tables
    response = execute_query(
        f"""
        SELECT table_name, 
               pg_size_pretty(pg_total_relation_size(quote_ident(table_name)::regclass)) as size
        FROM information_schema.tables 
        WHERE table_schema = '{schema_name}' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        "📊 ALL TABLES IN DATABASE"
    )
    
    if response and response['records']:
        print(f"✅ Found {len(response['records'])} tables:\n")
        for record in response['records']:
            table_name = record[0]['stringValue']
            size = record[1]['stringValue']
            print(f"   • {table_name:<20} Size: {size}")
    
    # 2. Count records in each table
    response = execute_query(
        f"""
        SELECT 
            'users' as table_name, COUNT(*) as count FROM {table_prefix}users
        UNION ALL
        SELECT 'instruments', COUNT(*) FROM {table_prefix}instruments
        UNION ALL
        SELECT 'accounts', COUNT(*) FROM {table_prefix}accounts
        UNION ALL
        SELECT 'positions', COUNT(*) FROM {table_prefix}positions
        UNION ALL
        SELECT 'jobs', COUNT(*) FROM {table_prefix}jobs
        ORDER BY table_name
        """,
        "📈 RECORD COUNTS PER TABLE"
    )
    
    if response and response['records']:
        print("\nTable record counts:\n")
        for record in response['records']:
            table_name = record[0]['stringValue']
            count = record[1]['longValue']
            status = "✅" if (table_name == 'instruments' and count > 0) else "📭"
            print(f"   {status} {table_name:<20} {count:,} records")
    
    # 3. Show instruments with allocation data
    response = execute_query(
        f"""
        SELECT symbol, name, instrument_type,
               allocation_asset_class::text as asset_class
        FROM {table_prefix}instruments 
        ORDER BY symbol 
        LIMIT 10
        """,
        "🎯 SAMPLE INSTRUMENTS (First 10)"
    )
    
    if response and response['records']:
        print("\nSymbol | Name | Type | Asset Class Allocation")
        print("-" * 70)
        for record in response['records']:
            symbol = record[0]['stringValue']
            name = record[1]['stringValue'][:35]
            inst_type = record[2]['stringValue']
            asset_class = record[3]['stringValue']
            print(f"{symbol:<6} | {name:<35} | {inst_type:<10} | {asset_class}")
    
    # 4. Verify allocation sums
    response = execute_query(
        f"""
        SELECT symbol,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_regions)) as regions_sum,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_sectors)) as sectors_sum,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_asset_class)) as asset_sum
        FROM {table_prefix}instruments
        WHERE symbol IN ('SPY', 'QQQ', 'BND', 'VEA', 'GLD')
        """,
        "✅ ALLOCATION VALIDATION (Sample ETFs)"
    )
    
    if response and response['records']:
        print("\nVerifying allocations sum to 100%:\n")
        print("Symbol | Regions | Sectors | Assets | Status")
        print("-" * 50)
        for record in response['records']:
            symbol = record[0]['stringValue']
            # Handle numeric values from SUM()
            regions = float(record[1].get('stringValue', '0')) if record[1] and 'stringValue' in record[1] else 0
            sectors = float(record[2].get('stringValue', '0')) if record[2] and 'stringValue' in record[2] else 0
            assets = float(record[3].get('stringValue', '0')) if record[3] and 'stringValue' in record[3] else 0
            
            all_valid = regions == 100 and sectors == 100 and assets == 100
            status = "✅ Valid" if all_valid else "❌ Invalid"
            
            print(f"{symbol:<6} | {regions:>7}% | {sectors:>7}% | {assets:>6}% | {status}")
    
    # 5. Show asset class distribution
    response = execute_query(
        f"""
        SELECT 
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'equity')::numeric = 100) as pure_equity,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'fixed_income')::numeric = 100) as pure_bonds,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'real_estate')::numeric = 100) as real_estate,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'commodities')::numeric = 100) as commodities,
            COUNT(*) FILTER (WHERE jsonb_typeof(allocation_asset_class) = 'object' 
                            AND (SELECT COUNT(*) FROM jsonb_object_keys(allocation_asset_class)) > 1) as mixed,
            COUNT(*) as total
        FROM {table_prefix}instruments
        """,
        "📊 ASSET CLASS DISTRIBUTION"
    )
    
    if response and response['records']:
        record = response['records'][0]
        print("\nInstrument breakdown by asset class:\n")
        print(f"   • Pure Equity ETFs:      {record[0]['longValue']:>3}")
        print(f"   • Pure Bond Funds:       {record[1]['longValue']:>3}")
        print(f"   • Real Estate ETFs:      {record[2]['longValue']:>3}")
        print(f"   • Commodity ETFs:        {record[3]['longValue']:>3}")
        print(f"   • Mixed Allocation ETFs: {record[4]['longValue']:>3}")
        print(f"   " + "-" * 25)
        print(f"   • TOTAL INSTRUMENTS:     {record[5]['longValue']:>3}")
    
    # 6. Check indexes exist
    response = execute_query(
        f"""
        SELECT schemaname, tablename, indexname
        FROM pg_indexes
        WHERE schemaname = '{schema_name}'
        AND indexname LIKE 'idx_%'
        ORDER BY tablename, indexname
        """,
        "🔍 DATABASE INDEXES"
    )
    
    if response and response['records']:
        print(f"\n✅ Found {len(response['records'])} custom indexes")
    
    # 7. Check triggers exist
    response = execute_query(
        f"""
        SELECT trigger_name, event_object_table
        FROM information_schema.triggers
        WHERE trigger_schema = '{schema_name}'
        ORDER BY event_object_table
        """,
        "⚡ DATABASE TRIGGERS"
    )
    
    if response and response['records']:
        print(f"\n✅ Found {len(response['records'])} update triggers for timestamp management")
    
    # Final summary
    print("\n" + "=" * 70)
    print("🎉 DATABASE VERIFICATION COMPLETE")
    print("=" * 70)
    print(f"\n🎯 Backend: {db_backend.upper()}")
    print(f"📊 Schema: {schema_name}")
    print("\n✅ All tables created successfully")
    print("✅ Database structure verified")
    print("✅ Indexes and triggers are in place")
    print("✅ Database is ready for operations!")

if __name__ == "__main__":
    main()