#!/usr/bin/env python3
"""
Simple test to check if test_user_001 exists in the database
"""

import os
from src.client import DataAPIClient
from src.models import Database
from dotenv import load_dotenv

load_dotenv(override=True)

# Initialize database
db = DataAPIClient()
db_models = Database()

print(f"🎯 Using {db.db_backend.upper()} backend")

# Try to find the test user
print("\n🔍 Searching for test_user_001...")

try:
    user = db_models.users.find_by_clerk_id('test_user_001')
    
    if user:
        print(f"✅ Found user: {user}")
        print(f"   • Display name: {user.get('display_name')}")
        print(f"   • Years until retirement: {user.get('years_until_retirement')}")
        print(f"   • Target retirement income: ${user.get('target_retirement_income'):,}")
        
        # Check user's accounts
        accounts = db_models.accounts.find_by_user('test_user_001')
        print(f"\n📦 User has {len(accounts)} accounts:")
        for acc in accounts:
            print(f"   • {acc['account_name']}: ${acc['cash_balance']:,}")
            
        # Check positions in first account if exists
        if accounts:
            positions = db_models.positions.find_by_account(accounts[0]['id'])
            print(f"\n📊 First account has {len(positions)} positions:")
            for pos in positions:
                print(f"   • {pos['symbol']}: {pos['quantity']} shares")
    else:
        print("❌ User test_user_001 not found!")
        
        # Let's see what users exist
        all_users = db.query("SELECT clerk_user_id, display_name FROM users LIMIT 10")
        print(f"\n📋 Found {len(all_users)} users in database:")
        for user in all_users:
            print(f"   • {user['clerk_user_id']}: {user['display_name']}")
            
except Exception as e:
    print(f"❌ Error searching for user: {e}")
    
    # Try direct SQL query
    try:
        print("\n🔧 Trying direct SQL query...")
        result = db.query("SELECT COUNT(*) as count FROM users WHERE clerk_user_id = 'test_user_001'")
        count = result[0]['count'] if result else 0
        print(f"   Direct query found {count} users with ID 'test_user_001'")
        
        # Show all users
        all_users = db.query("SELECT clerk_user_id, display_name FROM users LIMIT 10")
        print(f"\n📋 All users in database ({len(all_users)}):")
        for user in all_users:
            print(f"   • {user['clerk_user_id']}: {user['display_name']}")
            
    except Exception as e2:
        print(f"❌ Direct SQL query also failed: {e2}")