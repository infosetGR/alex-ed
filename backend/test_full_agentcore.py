#!/usr/bin/env python3
"""Full end-to-end test via SQS for the Alex platform using AgentCore agents"""

import os
import json
import boto3
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

from src import Database
from src.schemas import UserCreate, InstrumentCreate, AccountCreate, PositionCreate

def check_cloudwatch_logs(start_time: datetime, duration_minutes: int = 5):
    """Check CloudWatch logs for recent agent activity"""
    print(f"\n🔍 Checking CloudWatch logs (last {duration_minutes} minutes)...")
    
    logs_client = boto3.client('logs')
    
    # Agent log groups to check
    log_groups = [
        '/aws/lambda/alex-planner',
        '/aws/lambda/alex-tagger', 
        '/aws/lambda/alex-reporter',
        '/aws/lambda/alex-charter',
        '/aws/lambda/alex-retirement'
    ]
    
    end_time = datetime.now(timezone.utc)
    start_time_check = start_time - timedelta(minutes=1)  # Start a bit earlier
    
    for log_group in log_groups:
        try:
            # Check if log group exists
            logs_client.describe_log_groups(logGroupNamePrefix=log_group)
            
            # Get recent log events
            response = logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time_check.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000)
            )
            
            events = response.get('events', [])
            if events:
                agent_name = log_group.split('-')[-1].title()
                print(f"  📋 {agent_name}: {len(events)} log entries")
                
                # Show some key log messages
                for event in events[-3:]:  # Last 3 events
                    message = event.get('message', '').strip()
                    if any(keyword in message.lower() for keyword in ['error', 'fail', 'exception', 'success', 'completed']):
                        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000).strftime('%H:%M:%S')
                        print(f"    [{timestamp}] {message}")
            else:
                agent_name = log_group.split('-')[-1].title()
                print(f"  📋 {agent_name}: No recent activity")
                
        except Exception as e:
            agent_name = log_group.split('-')[-1].title()
            print(f"  ❌ {agent_name}: Could not check logs - {e}")
    
    print()

def setup_test_data(db):
    """Ensure test user and portfolio exist"""
    print("Setting up test data...")
    
    # Check/create test user
    test_user_id = 'test_user_001'
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        user_data = UserCreate(
            clerk_user_id=test_user_id,
            display_name="Test User",
            years_to_retirement=25,
            target_allocation={'stocks': 70, 'bonds': 20, 'alternatives': 10}
        )
        db.users.create(user_data.model_dump())
        print(f"  ✓ Created test user: {test_user_id}")
    else:
        print(f"  ✓ Test user exists: {test_user_id}")
    
    # Check/create test account
    accounts = db.accounts.find_by_user(test_user_id)
    if not accounts:
        account_data = AccountCreate(
            clerk_user_id=test_user_id,
            account_name="Test 401(k)",
            account_type="401k",
            cash_balance=5000.00
        )
        account_id = db.accounts.create(account_data.model_dump())
        print(f"  ✓ Created test account: Test 401(k)")
        
        # Add some positions
        positions = [
            {'symbol': 'SPY', 'quantity': 100},
            {'symbol': 'QQQ', 'quantity': 50},
            {'symbol': 'BND', 'quantity': 200},
            {'symbol': 'VUG', 'quantity': 75}  # Changed from VTI to VUG (available in DB)
        ]
        
        for pos in positions:
            position_data = PositionCreate(
                account_id=account_id,
                symbol=pos['symbol'],
                quantity=pos['quantity']
            )
            db.positions.create(position_data.model_dump())
        print(f"  ✓ Created {len(positions)} positions")
    else:
        print(f"  ✓ Test account exists with {len(db.positions.find_by_account(accounts[0]['id']))} positions")
    
    return test_user_id

def main():
    print("=" * 70)
    print("🎯 Full End-to-End Test via SQS (AgentCore Agents)")
    print("=" * 70)
    
    # Debug: Print environment info
    print("\n🔧 Environment Check:")
    print(f"  - AWS Region: {os.getenv('AWS_REGION', 'Not set')}")
    print(f"  - Bedrock Region: {os.getenv('BEDROCK_REGION', 'Not set')}")
    print(f"  - Database ARN: {os.getenv('DATABASE_CLUSTER_ARN', 'Not set')[:50]}...")
    print(f"  - Secret ARN: {os.getenv('DATABASE_SECRET_ARN', 'Not set')[:50]}...")
    
    db = Database()
    sqs = boto3.client('sqs')
    
    # Setup test data
    test_user_id = setup_test_data(db)
    
    # Create test job
    print("\nCreating analysis job...")
    job_data = {
        'clerk_user_id': test_user_id,
        'job_type': 'portfolio_analysis',
        'status': 'pending',
        'request_payload': {
            'analysis_type': 'full',
            'requested_at': datetime.now(timezone.utc).isoformat(),
            'test_run': True,
            'include_retirement': True,
            'include_charts': True,
            'include_report': True
        }
    }
    
    job_id = db.jobs.create(job_data)
    print(f"  ✓ Created job: {job_id}")
    
    # Get queue URL
    QUEUE_NAME = 'alex-analysis-jobs'
    response = sqs.list_queues(QueueNamePrefix=QUEUE_NAME)
    queue_url = None
    for url in response.get('QueueUrls', []):
        if QUEUE_NAME in url:
            queue_url = url
            break
    
    if not queue_url:
        print(f"  ❌ Queue {QUEUE_NAME} not found")
        return 1
    
    print(f"  ✓ Found queue: {QUEUE_NAME}")
    
    # Send message to SQS
    print("\nTriggering analysis via SQS (AgentCore orchestration)...")
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({'job_id': job_id})
    )
    print(f"  ✓ Message sent: {response['MessageId']}")
    print(f"  ✓ AgentCore agents will process: Planner → Tagger → Reporter + Charter + Retirement")
    
    # Monitor job progress
    print("\n⏳ Monitoring job progress...")
    print("-" * 50)
    
    start_time = time.time()
    timeout = 300  # 5 minutes (increased for debugging)
    last_status = None
    last_result_keys = set()
    
    # Keep track of what we've seen
    seen_agents = set()
    
    while time.time() - start_time < timeout:
        job = db.jobs.find_by_id(job_id)
        status = job['status']
        
        # Check for new result data
        current_result_keys = set()
        if job.get('report_payload'):
            current_result_keys.add('report')
        if job.get('charts_payload'):
            current_result_keys.add('charts')
        if job.get('retirement_payload'):
            current_result_keys.add('retirement')
        if job.get('summary_payload'):
            current_result_keys.add('summary')
        
        # Report new results
        new_results = current_result_keys - last_result_keys
        if new_results:
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}s] 📊 New results: {', '.join(new_results)}")
            last_result_keys = current_result_keys
        
        if status != last_status:
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}s] 📋 Status: {status}")
            last_status = status
            
            # Debug: Print more details about job state
            if status == 'running':
                print(f"       🔄 Job is being processed by agents")
            elif status == 'failed' and job.get('error_message'):
                print(f"       ❌ Error: {job.get('error_message')}")
                # Print more error details if available
                if job.get('error_details'):
                    print(f"       🔍 Details: {job.get('error_details')}")
        
        # Debug: Show what data we have so far
        if int(time.time() - start_time) % 10 == 0:  # Every 10 seconds
            elapsed = int(time.time() - start_time)
            data_summary = []
            if job.get('report_payload'):
                data_summary.append('report')
            if job.get('charts_payload'):
                data_summary.append('charts')
            if job.get('retirement_payload'):
                data_summary.append('retirement')
            if job.get('summary_payload'):
                data_summary.append('summary')
            
            if data_summary:
                print(f"[{elapsed:3d}s] 📊 Current data: {', '.join(data_summary)}")
            else:
                print(f"[{elapsed:3d}s] ⏳ Waiting for agent results...")
        
        if status == 'completed':
            print("-" * 50)
            print("\n✅ Job completed successfully!")
            
            # Check CloudWatch logs to see agent activity
            check_cloudwatch_logs(datetime.fromtimestamp(start_time, timezone.utc))
            
            print("\n📊 Analysis Results:")
            
            # Report
            if job.get('report_payload'):
                report_content = job['report_payload'].get('content', '')
                print(f"\n📝 Report Generated:")
                print(f"   - Length: {len(report_content)} characters")
                print(f"   - Preview: {report_content[:200]}...")
            else:
                print("\n❌ No report found")
            
            # Charts
            if job.get('charts_payload'):
                charts = job['charts_payload']
                print(f"\n📊 Charts Created: {len(charts)} visualizations")
                for chart_key, chart_data in charts.items():
                    if isinstance(chart_data, dict):
                        title = chart_data.get('title', 'Untitled')
                        chart_type = chart_data.get('type', 'unknown')
                        data_points = len(chart_data.get('data', []))
                        print(f"   - {chart_key}: {title} ({chart_type}, {data_points} data points)")
            else:
                print("\n❌ No charts found")
            
            # Retirement
            if job.get('retirement_payload'):
                retirement = job['retirement_payload']
                print(f"\n🎯 Retirement Analysis:")
                if isinstance(retirement, dict):
                    if 'success_rate' in retirement:
                        print(f"   - Success Rate: {retirement['success_rate']}%")
                    if 'projected_balance' in retirement:
                        print(f"   - Projected Balance: ${retirement['projected_balance']:,.0f}")
                    if 'analysis' in retirement:
                        print(f"   - Analysis Length: {len(retirement['analysis'])} characters")
            else:
                print("\n❌ No retirement analysis found")
            
            # Summary
            if job.get('summary_payload'):
                summary = job['summary_payload']
                print(f"\n📋 Summary:")
                if isinstance(summary, dict):
                    for key, value in summary.items():
                        if key != 'timestamp':
                            print(f"   - {key}: {value}")
            
            break
        elif status == 'failed':
            print("-" * 50)
            print(f"\n❌ Job failed")
            if job.get('error_message'):
                print(f"Error details: {job['error_message']}")
            
            # Check CloudWatch logs for more details
            check_cloudwatch_logs(datetime.fromtimestamp(start_time, timezone.utc))
            break
        
        time.sleep(2)
    else:
        print("-" * 50)
        print("\n❌ Job timed out after 5 minutes")
        print(f"Final status: {job['status']}")
        
        # Check CloudWatch logs for debugging
        check_cloudwatch_logs(datetime.fromtimestamp(start_time, timezone.utc))
        return 1
    
    print(f"\n📋 Job Details:")
    print(f"   - Job ID: {job_id}")
    print(f"   - User ID: {test_user_id}")
    print(f"   - Total Time: {int(time.time() - start_time)} seconds")
    
    return 0

if __name__ == "__main__":
    exit(main())