#!/usr/bin/env python3
"""Enhanced full end-to-end test with agent invocation tracking"""

import os
import json
import boto3
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

from src import Database
from src.schemas import UserCreate, InstrumentCreate, AccountCreate, PositionCreate

def check_agent_deployments():
    """Check if all required agents are deployed and their ARNs are in SSM"""
    print("\n🔍 Checking Agent Deployments:")
    print("-" * 40)
    
    ssm = boto3.client('ssm')
    agents = ['planner', 'reporter', 'charter', 'retirement', 'tagger']
    deployed_agents = {}
    
    for agent in agents:
        try:
            response = ssm.get_parameter(Name=f'/agents/{agent}_agent_arn')
            arn = response['Parameter']['Value']
            deployed_agents[agent] = arn
            print(f"  ✅ {agent.title()}: {arn}")
        except Exception as e:
            print(f"  ❌ {agent.title()}: Not found ({e})")
            deployed_agents[agent] = None
    
    return deployed_agents

def check_sqs_orchestrator():
    """Check SQS orchestrator configuration"""
    print("\n🔍 Checking SQS Configuration:")
    print("-" * 30)
    
    try:
        # Check if planner ARN is configured for SQS orchestrator
        ssm = boto3.client('ssm')
        response = ssm.get_parameter(Name='/agents/planner_agent_arn')
        planner_arn = response['Parameter']['Value']
        print(f"  ✅ Planner ARN: {planner_arn}")
        
        # Check if SQS queue exists
        sqs = boto3.client('sqs')
        response = sqs.list_queues(QueueNamePrefix='alex-analysis-jobs')
        if response.get('QueueUrls'):
            queue_url = response['QueueUrls'][0]
            print(f"  ✅ SQS Queue: {queue_url}")
            return queue_url
        else:
            print(f"  ❌ SQS Queue: alex-analysis-jobs not found")
            return None
            
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return None

def setup_test_data_with_instruments(db):
    """Setup test data and ensure we have some instruments that need tagging"""
    print("\n📊 Setting up enhanced test data...")
    
    # Setup basic test user and account
    test_user_id = 'test_user_enhanced'
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        user_data = UserCreate(
            clerk_user_id=test_user_id,
            display_name="Enhanced Test User",
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
            account_name="Enhanced Test 401(k)",
            account_type="401k",
            cash_balance=5000.00
        )
        account_id = db.accounts.create(account_data.model_dump())
        print(f"  ✓ Created test account: Enhanced Test 401(k)")
        
        # Add positions including one that will need tagging
        positions = [
            {'symbol': 'SPY', 'quantity': 100},  # Should exist with allocations
            {'symbol': 'QQQ', 'quantity': 50},   # Should exist with allocations
            {'symbol': 'BND', 'quantity': 200},  # Should exist with allocations
            {'symbol': 'TESTMISSING', 'quantity': 25},  # Will trigger tagger
        ]
        
        for pos in positions:
            # Check if instrument exists, if not create minimal version
            instrument = db.instruments.find_by_symbol(pos['symbol'])
            if not instrument and pos['symbol'] == 'TESTMISSING':
                # Create instrument without allocations to trigger tagger
                instrument_data = InstrumentCreate(
                    symbol='TESTMISSING',
                    name='Test Missing Allocations ETF',
                    instrument_type='etf',
                    current_price=100.0
                    # Deliberately omit allocation fields
                )
                db.instruments.create(instrument_data.model_dump())
                print(f"    ✓ Created test instrument: TESTMISSING (will trigger tagger)")
            
            position_data = PositionCreate(
                account_id=account_id,
                symbol=pos['symbol'],
                quantity=pos['quantity']
            )
            db.positions.create(position_data.model_dump())
        print(f"  ✓ Created {len(positions)} positions (including one for tagger test)")
    else:
        account_id = accounts[0]['id']
        positions = db.positions.find_by_account(account_id)
        print(f"  ✓ Test account exists with {len(positions)} positions")
    
    return test_user_id

def add_job_progress_tracking():
    """Add a simple progress tracking mechanism to the job"""
    # We'll patch the planner to write progress to a job_progress field
    # For now, let's create a helper that can check this
    pass

def enhanced_job_monitoring(db, job_id, start_time, timeout=300):
    """Enhanced job monitoring with detailed progress tracking"""
    print("\n⏳ Enhanced Job Monitoring:")
    print("-" * 50)
    
    last_status = None
    last_result_keys = set()
    check_count = 0
    
    while time.time() - start_time < timeout:
        check_count += 1
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
            print(f"[{elapsed:3d}s] 📊 NEW RESULTS: {', '.join(new_results)}")
            last_result_keys = current_result_keys
        
        if status != last_status:
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}s] 📋 Status: {status}")
            last_status = status
            
            if status == 'running':
                print(f"       🔄 Job is being processed by AgentCore planner")
            elif status == 'failed' and job.get('error_message'):
                print(f"       ❌ Error: {job.get('error_message')}")
        
        # Every 15 seconds, show detailed status
        if check_count % 8 == 0:  # Every ~15 seconds (2s * 8)
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}s] 🔍 Deep check:")
            print(f"       Job status: {status}")
            print(f"       Data available: {', '.join(current_result_keys) if current_result_keys else 'None'}")
            
            # Try to peek at some result content
            if job.get('report_payload'):
                content = job['report_payload'].get('content', '')
                if content:
                    print(f"       Report preview: {content[:100]}...")
            
            if job.get('charts_payload'):
                charts = job['charts_payload']
                if isinstance(charts, dict):
                    print(f"       Charts: {len(charts)} visualizations")
            
            if job.get('retirement_payload'):
                retirement = job['retirement_payload']
                if isinstance(retirement, dict) and 'success_rate' in retirement:
                    print(f"       Retirement: {retirement['success_rate']}% success rate")
        
        if status == 'completed':
            print("-" * 50)
            print("\n✅ Job completed!")
            return analyze_job_results(job)
        elif status == 'failed':
            print("-" * 50)
            print(f"\n❌ Job failed: {job.get('error_message', 'Unknown error')}")
            return False
        
        time.sleep(2)
    
    print("-" * 50)
    print(f"\n⏰ Job timed out after {timeout//60} minutes")
    print(f"Final status: {job['status']}")
    return False

def analyze_job_results(job):
    """Analyze and display job results in detail"""
    print("\n📊 Detailed Results Analysis:")
    print("=" * 60)
    
    success = True
    
    # Report analysis
    if job.get('report_payload'):
        report = job['report_payload']
        if isinstance(report, dict) and report.get('content'):
            content = report['content']
            print(f"\n📝 REPORT GENERATED:")
            print(f"   Length: {len(content)} characters")
            print(f"   Preview: {content[:300]}...")
            if len(content) > 300:
                print(f"   ... (truncated, {len(content)-300} more chars)")
        else:
            print(f"\n❌ REPORT: Invalid format or empty")
            success = False
    else:
        print(f"\n❌ REPORT: Missing")
        success = False
    
    # Charts analysis
    if job.get('charts_payload'):
        charts = job['charts_payload']
        if isinstance(charts, dict) and charts:
            print(f"\n📊 CHARTS GENERATED:")
            print(f"   Count: {len(charts)} visualizations")
            for chart_key, chart_data in list(charts.items())[:3]:  # Show first 3
                if isinstance(chart_data, dict):
                    title = chart_data.get('title', 'Untitled')
                    chart_type = chart_data.get('type', 'unknown')
                    data_points = len(chart_data.get('data', []))
                    print(f"   - {chart_key}: {title} ({chart_type}, {data_points} points)")
            if len(charts) > 3:
                print(f"   ... and {len(charts)-3} more charts")
        else:
            print(f"\n❌ CHARTS: Invalid format or empty")
            success = False
    else:
        print(f"\n❌ CHARTS: Missing")
        success = False
    
    # Retirement analysis
    if job.get('retirement_payload'):
        retirement = job['retirement_payload']
        if isinstance(retirement, dict):
            print(f"\n🎯 RETIREMENT ANALYSIS:")
            if 'success_rate' in retirement:
                print(f"   Success Rate: {retirement['success_rate']}%")
            if 'projected_balance' in retirement:
                print(f"   Projected Balance: ${retirement['projected_balance']:,.0f}")
            if 'analysis' in retirement:
                analysis = retirement['analysis']
                print(f"   Analysis: {analysis[:200]}...")
        else:
            print(f"\n❌ RETIREMENT: Invalid format")
            success = False
    else:
        print(f"\n❌ RETIREMENT: Missing")
        success = False
    
    # Summary
    if job.get('summary_payload'):
        summary = job['summary_payload']
        print(f"\n📋 SUMMARY: Available")
        if isinstance(summary, dict):
            for key, value in summary.items():
                if key != 'timestamp':
                    print(f"   {key}: {value}")
    
    return success

def main():
    print("=" * 80)
    print("🎯 ENHANCED AGENT INVOCATION TEST")
    print("=" * 80)
    
    # Pre-flight checks
    print("\n🚀 Pre-flight Checks:")
    
    # Check environment
    print(f"\n🔧 Environment:")
    print(f"  - AWS Region: {os.getenv('AWS_REGION', 'Not set')}")
    print(f"  - Bedrock Region: {os.getenv('BEDROCK_REGION', 'Not set')}")
    print(f"  - Database ARN: {os.getenv('DATABASE_CLUSTER_ARN', 'Not set')[:50]}...")
    
    # Check agent deployments
    deployed_agents = check_agent_deployments()
    missing_agents = [name for name, arn in deployed_agents.items() if not arn]
    if missing_agents:
        print(f"\n❌ Missing agents: {missing_agents}")
        print("Run: uv run terraform/6_agents/deploy_agents.py <agent_name>")
        return 1
    
    # Check SQS
    queue_url = check_sqs_orchestrator()
    if not queue_url:
        return 1
    
    # Initialize database
    db = Database()
    sqs = boto3.client('sqs')
    
    # Setup test data (including instrument that needs tagging)
    test_user_id = setup_test_data_with_instruments(db)
    
    # Create enhanced analysis job
    print(f"\n📋 Creating enhanced analysis job...")
    job_data = {
        'clerk_user_id': test_user_id,
        'job_type': 'portfolio_analysis',
        'status': 'pending',
        'request_payload': {
            'analysis_type': 'full',
            'requested_at': datetime.now(timezone.utc).isoformat(),
            'test_run': True,
            'enhanced_test': True,
            'include_retirement': True,
            'include_charts': True,
            'include_report': True,
            'force_tagging': True  # This could trigger tagger even if not needed
        }
    }
    
    job_id = db.jobs.create(job_data)
    print(f"  ✓ Created job: {job_id}")
    
    # Send to SQS
    print(f"\n🚀 Triggering AgentCore orchestration...")
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({'job_id': job_id})
    )
    print(f"  ✓ Message sent: {response['MessageId']}")
    print(f"  ✓ Expected flow: SQS → Planner → Reporter + Charter + Retirement (+ Tagger if needed)")
    
    # Enhanced monitoring
    start_time = time.time()
    success = enhanced_job_monitoring(db, job_id, start_time)
    
    # Final summary
    elapsed_time = int(time.time() - start_time)
    print(f"\n📊 Test Summary:")
    print(f"   Job ID: {job_id}")
    print(f"   User ID: {test_user_id}")
    print(f"   Total Time: {elapsed_time} seconds")
    print(f"   Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
    
    if not success:
        print(f"\n🔍 Troubleshooting Tips:")
        print(f"   1. Check AgentCore logs in AWS Console → Bedrock → Agent Runtimes")
        print(f"   2. Verify all agents have permissions to write to Aurora")
        print(f"   3. Check if planner is actually calling other agents")
        print(f"   4. Run: aws logs tail /aws/lambda/alex-sqs-orchestrator --follow")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())