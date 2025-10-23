"""
Test the Charter Agent with Bedrock AgentCore (full test).
"""

import os
import json
import uuid
import asyncio
from typing import Dict, Any

# Import database
from src import Database

def create_comprehensive_portfolio() -> Dict[str, Any]:
    """Create a comprehensive test portfolio with multiple accounts and positions."""
    return {
        "user_id": "charter_full_test",
        "job_id": str(uuid.uuid4()),
        "accounts": [
            {
                "id": "charter_401k",
                "name": "Company 401(k)",
                "type": "401k",
                "cash_balance": 8500.0,
                "positions": [
                    {
                        "symbol": "SPY",
                        "quantity": 150.0,
                        "instrument": {
                            "symbol": "SPY",
                            "name": "SPDR S&P 500 ETF",
                            "current_price": 455.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {
                                "technology": 28,
                                "healthcare": 13,
                                "financials": 13,
                                "consumer_discretionary": 10,
                                "industrials": 8,
                                "consumer_staples": 7,
                                "energy": 4,
                                "real_estate": 3,
                                "utilities": 3,
                                "materials": 2,
                                "telecommunications": 9
                            }
                        }
                    },
                    {
                        "symbol": "BND",
                        "quantity": 100.0,
                        "instrument": {
                            "symbol": "BND",
                            "name": "Vanguard Total Bond Market ETF", 
                            "current_price": 76.5,
                            "allocation_asset_class": {"fixed_income": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {"government": 65, "corporate": 35}
                        }
                    },
                    {
                        "symbol": "VEA",
                        "quantity": 80.0,
                        "instrument": {
                            "symbol": "VEA",
                            "name": "Vanguard FTSE Developed Markets ETF",
                            "current_price": 48.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"europe": 60, "asia_pacific": 40},
                            "allocation_sectors": {
                                "technology": 15,
                                "healthcare": 14,
                                "financials": 18,
                                "consumer_discretionary": 12,
                                "industrials": 14,
                                "consumer_staples": 9,
                                "energy": 5,
                                "materials": 8,
                                "telecommunications": 5
                            }
                        }
                    }
                ]
            },
            {
                "id": "charter_roth",
                "name": "Roth IRA",
                "type": "roth_ira", 
                "cash_balance": 3200.0,
                "positions": [
                    {
                        "symbol": "QQQ",
                        "quantity": 45.0,
                        "instrument": {
                            "symbol": "QQQ",
                            "name": "Invesco QQQ Trust",
                            "current_price": 385.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {
                                "technology": 55,
                                "consumer_discretionary": 15,
                                "healthcare": 8,
                                "telecommunications": 7,
                                "industrials": 5,
                                "consumer_staples": 4,
                                "utilities": 3,
                                "energy": 1,
                                "materials": 1,
                                "financials": 1
                            }
                        }
                    },
                    {
                        "symbol": "VNQ",
                        "quantity": 35.0,
                        "instrument": {
                            "symbol": "VNQ",
                            "name": "Vanguard Real Estate ETF",
                            "current_price": 92.0,
                            "allocation_asset_class": {"real_estate": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {"real_estate": 100}
                        }
                    }
                ]
            },
            {
                "id": "charter_taxable",
                "name": "Taxable Brokerage",
                "type": "taxable",
                "cash_balance": 12000.0,
                "positions": [
                    {
                        "symbol": "VTI",
                        "quantity": 120.0,
                        "instrument": {
                            "symbol": "VTI",
                            "name": "Vanguard Total Stock Market ETF",
                            "current_price": 235.0,
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
                    },
                    {
                        "symbol": "VXUS",
                        "quantity": 90.0,
                        "instrument": {
                            "symbol": "VXUS", 
                            "name": "Vanguard Total International Stock ETF",
                            "current_price": 58.0,
                            "allocation_asset_class": {"equity": 100},
                            "allocation_regions": {"europe": 40, "asia_pacific": 35, "emerging_markets": 25},
                            "allocation_sectors": {
                                "technology": 18,
                                "financials": 16,
                                "healthcare": 12,
                                "industrials": 12,
                                "consumer_discretionary": 11,
                                "consumer_staples": 8,
                                "materials": 7,
                                "energy": 6,
                                "telecommunications": 5,
                                "utilities": 3,
                                "real_estate": 2
                            }
                        }
                    },
                    {
                        "symbol": "VTEB",
                        "quantity": 60.0,
                        "instrument": {
                            "symbol": "VTEB",
                            "name": "Vanguard Tax-Exempt Bond ETF",
                            "current_price": 52.0,
                            "allocation_asset_class": {"fixed_income": 100},
                            "allocation_regions": {"north_america": 100},
                            "allocation_sectors": {"municipal": 100}
                        }
                    }
                ]
            }
        ]
    }

def test_charter_agent_full():
    """Test the charter agent with comprehensive portfolio data."""
    print("🎨 Testing Charter Agent (Full Bedrock Test)...")
    
    # Create comprehensive test data
    portfolio_data = create_comprehensive_portfolio()
    job_id = portfolio_data["job_id"]
    user_id = portfolio_data["user_id"]
    
    print(f"📊 Job ID: {job_id}")
    print(f"👤 User ID: {user_id}")
    
    # Calculate comprehensive portfolio statistics
    total_value = 0.0
    total_cash = 0.0
    account_values = {}
    position_count = 0
    
    for account in portfolio_data["accounts"]:
        cash_balance = float(account.get("cash_balance", 0))
        total_cash += cash_balance
        total_value += cash_balance
        
        account_value = cash_balance
        
        for position in account["positions"]:
            quantity = float(position["quantity"])
            price = float(position["instrument"]["current_price"])
            position_value = quantity * price
            account_value += position_value
            total_value += position_value
            position_count += 1
        
        account_values[account["name"]] = account_value
    
    print(f"💰 Total Portfolio Value: ${total_value:,.2f}")
    print(f"💵 Total Cash: ${total_cash:,.2f}")
    print(f"📈 Total Positions: {position_count}")
    print(f"🏦 Accounts: {len(portfolio_data['accounts'])}")
    
    for name, value in account_values.items():
        pct = (value / total_value * 100) if total_value > 0 else 0
        print(f"   {name}: ${value:,.2f} ({pct:.1f}%)")
    
    try:
        # Initialize database
        db = Database()
        print("\n📊 Database connected")
        
        # Create or find user
        try:
            user = db.users.find_by_clerk_id(user_id)
            if not user:
                user_data = {
                    'clerk_user_id': user_id,
                    'display_name': 'Charter FullTest',
                    'years_until_retirement': 30
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
                'request_payload': {'test': 'full test of charter agent with comprehensive portfolio'}
            }
            job = db.jobs.create(job_data)
            print(f"💼 Created job: {job_id}")
        except Exception as e:
            print(f"⚠️ Job creation warning: {e}")
        
        # Import and run the charter agent
        print("\n🎨 Running Charter Agent with Bedrock AgentCore...")
        from agent import create_agent_and_run
        
        result = create_agent_and_run(job_id, portfolio_data, user_id)
        
        print("\n📊 Charter Agent Full Test Result:")
        print("=" * 60)
        
        # Parse and analyze the result
        try:
            parsed_result = json.loads(result)
            
            if "error" in parsed_result:
                print(f"❌ Error: {parsed_result['error']}")
            elif "charts" in parsed_result:
                charts = parsed_result["charts"]
                print(f"✅ Successfully generated {len(charts)} visualization charts!")
                
                # Analyze each chart in detail
                for i, chart in enumerate(charts, 1):
                    print(f"\n📈 Chart {i}: {chart.get('title', 'Untitled Chart')}")
                    print(f"   🔑 Key: {chart.get('key', 'unknown')}")
                    print(f"   📊 Type: {chart.get('type', 'unknown')}")
                    print(f"   📝 Description: {chart.get('description', 'No description')}")
                    
                    data_points = chart.get('data', [])
                    print(f"   📋 Data Points: {len(data_points)}")
                    
                    # Calculate total value in this chart for validation
                    total_chart_value = sum(point.get('value', 0) for point in data_points)
                    print(f"   💰 Total Chart Value: ${total_chart_value:,.2f}")
                    
                    # Show all data points for detailed analysis
                    for j, point in enumerate(data_points):
                        name = point.get('name', 'Unknown')
                        value = point.get('value', 0)
                        color = point.get('color', 'No color')
                        pct = (value / total_chart_value * 100) if total_chart_value > 0 else 0
                        print(f"     {j+1:2d}. {name:20s}: ${value:10,.2f} ({pct:5.1f}%) {color}")
                
                # Save charts to database
                try:
                    charts_data = {}
                    for chart in charts:
                        chart_key = chart.get('key', f"chart_{len(charts_data) + 1}")
                        chart_copy = {k: v for k, v in chart.items() if k != 'key'}
                        charts_data[chart_key] = chart_copy
                    
                    success = db.jobs.update_charts(job_id, charts_data)
                    if success:
                        print(f"\n💾 All {len(charts)} charts saved to database successfully!")
                        print(f"   Chart keys: {list(charts_data.keys())}")
                    else:
                        print(f"\n⚠️ Failed to save charts to database")
                        
                except Exception as e:
                    print(f"\n⚠️ Database save error: {e}")
            else:
                print("❓ Unexpected result format")
                print("Raw result preview:")
                print(result[:1000] + "..." if len(result) > 1000 else result)
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON result: {e}")
            print("Raw result preview:")
            print(result[:1000] + "..." if len(result) > 1000 else result)
        
        print("\n" + "=" * 60)
        print("✅ Charter Agent Full Test completed!")
        
    except Exception as e:
        print(f"❌ Error during Charter Agent full test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_charter_agent_full()