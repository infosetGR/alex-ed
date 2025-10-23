"""
Test the Charter Agent with database integration (simple test).
"""

import os
import json
import uuid
import asyncio
from typing import Dict, Any

# Import database
from src import Database

# Import the agent
from agent import create_agent_and_run

def create_test_portfolio_data() -> Dict[str, Any]:
    """Create test portfolio data for charter agent."""
    return {
        "user_id": "test_user_charter",
        "job_id": str(uuid.uuid4()),
        "accounts": [
            {
                "id": "charter_acc1",
                "name": "401(k)",
                "type": "401k",
                "cash_balance": 5000.0,
                "positions": [
                    {
                        "symbol": "SPY",
                        "quantity": 100.0,
                        "instrument": {
                            "symbol": "SPY",
                            "name": "SPDR S&P 500 ETF",
                            "current_price": 450.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {
                                "technology": 30,
                                "healthcare": 15,
                                "financials": 15,
                                "consumer_discretionary": 20,
                                "industrials": 20
                            }
                        }
                    },
                    {
                        "symbol": "BND",
                        "quantity": 50.0,
                        "instrument": {
                            "symbol": "BND",
                            "name": "Vanguard Total Bond Market ETF",
                            "current_price": 75.0,
                            "allocation_asset_class": {"fixed_income": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {"government": 70, "corporate": 30}
                        }
                    }
                ]
            },
            {
                "id": "charter_acc2",
                "name": "Roth IRA",
                "type": "roth_ira",
                "cash_balance": 2500.0,
                "positions": [
                    {
                        "symbol": "VTI",
                        "quantity": 75.0,
                        "instrument": {
                            "symbol": "VTI",
                            "name": "Vanguard Total Stock Market ETF",
                            "current_price": 220.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {
                                "technology": 25,
                                "healthcare": 14,
                                "financials": 13,
                                "consumer_discretionary": 12,
                                "industrials": 9,
                                "consumer_staples": 6,
                                "energy": 4,
                                "real_estate": 4,
                                "utilities": 3,
                                "materials": 3,
                                "telecommunications": 7
                            }
                        }
                    }
                ]
            }
        ]
    }

def test_charter_agent():
    """Test the charter agent with portfolio data."""
    print("🎨 Testing Charter Agent...")
    
    # Create test data
    portfolio_data = create_test_portfolio_data()
    job_id = portfolio_data["job_id"]
    user_id = portfolio_data["user_id"]
    
    print(f"📊 Job ID: {job_id}")
    print(f"👤 User ID: {user_id}")
    
    # Calculate total portfolio value for context
    total_value = 0.0
    for account in portfolio_data["accounts"]:
        total_value += float(account.get("cash_balance", 0))
        for position in account["positions"]:
            quantity = float(position["quantity"])
            price = float(position["instrument"]["current_price"])
            total_value += quantity * price
    
    print(f"💰 Total Portfolio Value: ${total_value:,.2f}")
    
    try:
        # Initialize database
        db = Database()
        print("📊 Database connected")
        
        # Create or find user
        try:
            user = db.users.find_by_clerk_id(user_id)
            if not user:
                user_data = {
                    'clerk_user_id': user_id,
                    'display_name': 'Charter Test',
                    'years_until_retirement': 25
                }
                user = db.users.create(user_data)
                print(f"👤 Created test user: {user_id}")
            else:
                print(f"👤 Found existing user: {user_id}")
        except Exception as e:
            print(f"⚠️ User setup warning: {e}")
        
        # Create job entry
        try:
            job_data = {
                'id': job_id,
                'clerk_user_id': user_id,
                'job_type': 'portfolio_analysis',
                'status': 'processing',
                'request_payload': {'test': 'charter agent charts generation'}
            }
            job = db.jobs.create(job_data)
            print(f"💼 Created job: {job_id}")
        except Exception as e:
            print(f"⚠️ Job creation warning: {e}")
        
        # Run the charter agent
        print("\n🎨 Running Charter Agent...")
        result = create_agent_and_run(job_id, portfolio_data, user_id)
        
        print("📊 Charter Agent Result:")
        print("=" * 50)
        
        # Try to parse and format the JSON result
        try:
            parsed_result = json.loads(result)
            
            if "error" in parsed_result:
                print(f"❌ Error: {parsed_result['error']}")
            elif "charts" in parsed_result:
                charts = parsed_result["charts"]
                print(f"✅ Generated {len(charts)} charts:")
                
                for i, chart in enumerate(charts, 1):
                    print(f"\n📈 Chart {i}: {chart.get('title', 'Untitled')}")
                    print(f"   Type: {chart.get('type', 'unknown')}")
                    print(f"   Key: {chart.get('key', 'unknown')}")
                    print(f"   Description: {chart.get('description', 'No description')}")
                    
                    data_points = chart.get('data', [])
                    print(f"   Data Points: {len(data_points)}")
                    
                    # Show first few data points
                    for j, point in enumerate(data_points[:3]):
                        name = point.get('name', 'Unknown')
                        value = point.get('value', 0)
                        color = point.get('color', 'No color')
                        print(f"     {j+1}. {name}: ${value:,.2f} ({color})")
                    
                    if len(data_points) > 3:
                        print(f"     ... and {len(data_points) - 3} more")
                
                # Save charts to database if possible
                try:
                    charts_data = {}
                    for chart in charts:
                        chart_key = chart.get('key', f"chart_{len(charts_data) + 1}")
                        chart_copy = {k: v for k, v in chart.items() if k != 'key'}
                        charts_data[chart_key] = chart_copy
                    
                    success = db.jobs.update_charts(job_id, charts_data)
                    if success:
                        print(f"\n💾 Charts saved to database successfully")
                    else:
                        print(f"\n⚠️ Failed to save charts to database")
                        
                except Exception as e:
                    print(f"\n⚠️ Database save error: {e}")
            else:
                print("❓ Unexpected result format")
                print(result)
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON result: {e}")
            print("Raw result:")
            print(result)
        
        print("\n" + "=" * 50)
        print("✅ Charter Agent test completed")
        
    except Exception as e:
        print(f"❌ Error during Charter Agent test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_charter_agent()