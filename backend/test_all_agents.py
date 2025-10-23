#!/usr/bin/env python3
"""
Test all agents working together through the planner orchestration.
This test creates a realistic portfolio analysis job and monitors all agent invocations.
"""

import json
import time
import boto3
import uuid
from datetime import datetime, timezone

# Import shared utilities
from job_progress import add_job_progress, get_job_progress
from database.src import Database

def get_planner_queue_url():
    """Get the SQS queue URL for the planner."""
    sqs = boto3.client('sqs')
    QUEUE_NAME = 'alex-analysis-jobs'
    response = sqs.list_queues(QueueNamePrefix=QUEUE_NAME)
    
    for url in response.get('QueueUrls', []):
        if QUEUE_NAME in url:
            return url
    
    raise Exception(f"Queue {QUEUE_NAME} not found")

def test_all_agents():
    """Test comprehensive agent orchestration with detailed monitoring."""
    
    print("🚀 Starting comprehensive agent orchestration test...")
    
    # Initialize services
    db = Database()
    sqs = boto3.client('sqs')
    
    # Create test data
    test_user_id = "user_test_comprehensive"
    job_id = str(uuid.uuid4())
    
    print(f"📋 Test job ID: {job_id}")
    print(f"👤 Test user ID: {test_user_id}")
    
    # Ensure test user exists
    existing_user = db.users.find_by_clerk_id(test_user_id)
    if not existing_user:
        db.users.create({
            "clerk_user_id": test_user_id,
            "display_name": "Test User",
            "years_until_retirement": 30,
            "target_retirement_income": 75000.0,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        print("✅ Created test user")
    
    # Create test account
    account_id = str(uuid.uuid4())  # Use proper UUID for account
    db.accounts.create({
        "id": account_id,
        "clerk_user_id": test_user_id,
        "account_name": "Test Portfolio",
        "account_purpose": "Investment testing",
        "cash_balance": 50000.0
    })
    print(f"✅ Created test account: {account_id}")
    
    # Create test positions with existing instruments (from check_db.py output)
    test_positions = [
        {"symbol": "VTI", "quantity": 100},  # Total Stock Market
        {"symbol": "BND", "quantity": 200},  # Total Bond Market
        {"symbol": "VNQ", "quantity": 25},   # Real Estate
        {"symbol": "SPY", "quantity": 15},   # S&P 500
        {"symbol": "QQQ", "quantity": 10}    # Nasdaq
    ]
    
    for position in test_positions:
        db.positions.create({
            "account_id": account_id,
            "symbol": position["symbol"],
            "quantity": position["quantity"]
        })
    
    print(f"✅ Created {len(test_positions)} test positions")
    
    # Create comprehensive portfolio data
    portfolio_data = {
        "user_id": test_user_id,
        "accounts": [
            {
                "id": account_id,
                "name": "Test Portfolio",
                "purpose": "Investment testing",
                "cash_balance": 50000.0,
                "positions": test_positions
            }
        ]
    }
    
    # Create analysis request
    analysis_request = {
        "analysis_type": "comprehensive",
        "user_preferences": {
            "risk_tolerance": "moderate",
            "investment_horizon": "long-term",
            "age": 35,
            "retirement_age": 65,
            "annual_income": 100000,
            "annual_expenses": 60000
        },
        "report_sections": ["portfolio_summary", "allocation_analysis", "performance_metrics", "retirement_projection"],
        "include_charts": True
    }
    
    # Create job record
    db.jobs.create({
        "id": job_id,
        "clerk_user_id": test_user_id,
        "job_type": "portfolio_analysis",
        "status": "submitted",
        "request_payload": {
            "portfolio_data": portfolio_data,
            "analysis_request": analysis_request
        },
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    print("✅ Created job record")
    
    # Add initial progress (skip if error)
    try:
        add_job_progress(db, job_id, "Comprehensive analysis job created", "test")
    except Exception as e:
        print(f"⚠️ Could not add initial progress: {e}")
    
    # Submit job to SQS queue
    queue_url = get_planner_queue_url()
    message_body = json.dumps({
        "job_id": job_id,
        "analysis_request": analysis_request
    })
    
    print(f"📤 Submitting job to queue: {queue_url}")
    
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=message_body
    )
    
    print(f"✅ Message sent with ID: {response['MessageId']}")
    
    # Monitor job progress
    print("\n🔍 Monitoring agent invocations...")
    print("=" * 60)
    
    max_wait_time = 300  # 5 minutes
    start_time = time.time()
    last_progress_count = 0
    
    # Expected agents for comprehensive analysis
    expected_agents = ["planner", "tagger", "reporter", "charter", "retirement"]
    agents_invoked = set()
    
    while time.time() - start_time < max_wait_time:
        try:
            # Check job status
            job = db.jobs.find_by_id(job_id)
            if job:
                current_status = job.get("status", "unknown")
                print(f"📊 Job status: {current_status}")
                
                # Get progress updates (fix function call)
                try:
                    progress_updates = get_job_progress(db, job_id)
                except Exception as e:
                    print(f"❌ Error getting progress: {e}")
                    progress_updates = []
                
                if len(progress_updates) > last_progress_count:
                    new_updates = progress_updates[last_progress_count:]
                    for update in new_updates:
                        timestamp = update.get("timestamp", "unknown")
                        action = update.get("action", "unknown")
                        details = update.get("details", "")
                        
                        print(f"🔔 [{timestamp}] {action}: {details}")
                        
                        # Track which agents have been invoked
                        for agent in expected_agents:
                            if agent in action.lower() or agent in details.lower():
                                agents_invoked.add(agent)
                    
                    last_progress_count = len(progress_updates)
                
                # Check if job is complete
                if current_status in ["completed", "failed", "error"]:
                    print(f"\n🏁 Job finished with status: {current_status}")
                    
                    # Show final results
                    if job.get("results"):
                        print("📋 Job Results:")
                        results = job["results"]
                        if isinstance(results, str):
                            try:
                                results = json.loads(results)
                            except:
                                pass
                        print(json.dumps(results, indent=2)[:1000] + "..." if len(str(results)) > 1000 else json.dumps(results, indent=2))
                    
                    break
                
            else:
                print("❌ Job record not found")
                break
                
        except Exception as e:
            print(f"❌ Error checking job status: {e}")
        
        print("⏳ Waiting 10 seconds...")
        time.sleep(10)
    
    # Final analysis
    print("\n" + "=" * 60)
    print("📊 FINAL ANALYSIS")
    print("=" * 60)
    
    final_job = db.jobs.find_by_id(job_id)
    if final_job:
        print(f"Final Status: {final_job.get('status', 'unknown')}")
        
        # Check which agents were invoked
        print(f"\nAgents Expected: {', '.join(expected_agents)}")
        print(f"Agents Invoked: {', '.join(sorted(agents_invoked)) if agents_invoked else 'None detected'}")
        
        missing_agents = set(expected_agents) - agents_invoked
        if missing_agents:
            print(f"❌ Missing Agents: {', '.join(missing_agents)}")
        else:
            print("✅ All expected agents were invoked!")
        
        # Show progress timeline
        final_progress = get_job_progress(db, job_id)
        print(f"\nTotal Progress Updates: {len(final_progress)}")
        
        if final_progress:
            print("\n📈 Progress Timeline:")
            for i, update in enumerate(final_progress[-10:], 1):  # Show last 10 updates
                print(f"  {i}. [{update.get('timestamp', 'unknown')}] {update.get('action', 'unknown')}")
    
    # Cleanup
    print(f"\n🧹 Cleaning up test data...")
    try:
        # Delete positions
        positions = db.positions.find_by_account(account_id)
        for position in positions:
            db.positions.delete(position["id"])
        
        # Delete account
        db.accounts.delete(account_id)
        
        # Keep job record for analysis but mark as test
        db.jobs.update(job_id, {"status": "test_completed"})
        
        print("✅ Cleanup completed")
    except Exception as e:
        print(f"⚠️ Cleanup error (non-critical): {e}")
    
    print(f"\n🎯 Test completed! Job ID for reference: {job_id}")
    
    return {
        "job_id": job_id,
        "agents_invoked": list(agents_invoked),
        "expected_agents": expected_agents,
        "all_agents_invoked": len(agents_invoked) == len(expected_agents),
        "final_status": final_job.get("status") if final_job else "unknown"
    }

if __name__ == "__main__":
    result = test_all_agents()
    print(f"\n🏆 TEST RESULT: {json.dumps(result, indent=2)}")