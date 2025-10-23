"""
Financial Planner Orchestrator Agent - AgentCore Implementation

This agent coordinates portfolio analysis across specialized agents using
the invoke_agent_with_boto3 pattern for orchestration.
"""

import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# Load environment variables from SSM at startup
import sys
sys.path.append('/opt/python')  # Add common layer path if available
try:
    from utils import load_env_from_ssm
    load_env_from_ssm()
    print("✅ Loaded environment variables from SSM")
except Exception as e:
    print(f"⚠️ Could not load environment from SSM: {e}")
    # Fallback to local .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Loaded environment variables from .env file")
    except ImportError:
        print("⚠️ python-dotenv not available, skipping .env file loading")
    except Exception as e2:
        print(f"⚠️ Could not load .env file: {e2}")

from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Import parent directory utils
import sys
import os

# Add current directory to Python path for src imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tools import get_agent_arn, invoke_agent_with_boto3
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'database')))

# Import database
from src import Database

# Add job progress tracking
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
try:
    from job_progress import add_job_progress
except ImportError:
    # Fallback if job_progress module not available
    def add_job_progress(db, job_id, message, agent=None, details=None):
        logger.info(f"Progress: {message}")

logger = logging.getLogger(__name__)



def load_portfolio_summary(job_id: str, db: Database) -> Dict[str, Any]:
    """Load basic portfolio summary statistics."""
    try:
        job = db.jobs.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        user_id = job["clerk_user_id"]
        user = db.users.find_by_clerk_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        accounts = db.accounts.find_by_user(user_id)
        
        # Calculate simple summary statistics
        total_value = 0.0
        total_positions = 0
        total_cash = 0.0
        
        for account in accounts:
            total_cash += float(account.get("cash_balance", 0))
            positions = db.positions.find_by_account(account["id"])
            total_positions += len(positions)
            
            # Add position values
            for position in positions:
                instrument = db.instruments.find_by_symbol(position["symbol"])
                if instrument and instrument.get("current_price"):
                    price = float(instrument["current_price"])
                    quantity = float(position["quantity"])
                    total_value += price * quantity
        
        total_value += total_cash
        
        # Return only summary statistics
        return {
            "total_value": total_value,
            "num_accounts": len(accounts),
            "num_positions": total_positions,
            "years_until_retirement": user.get("years_until_retirement", 30),
            "target_retirement_income": float(user.get("target_retirement_income", 80000))
        }

    except Exception as e:
        logger.error(f"Error loading portfolio summary: {e}")
        raise

@tool
async def invoke_reporter_agent(job_id: str) -> str:
    """
    Invoke the Report Writer agent to generate portfolio analysis narrative.
    
    Args:
        job_id: The job ID for the analysis
        
    Returns:
        Analysis result message
    """
    try:
        # Get database instance
        db = Database()
        
        agent_arn = get_agent_arn("reporter")
        if not agent_arn:
            add_job_progress(db, job_id, "Error: Could not find Reporter agent ARN", "planner")
            return "Error: Could not find Reporter agent ARN"

        session_id = f"planner-{job_id}-{int(datetime.now().timestamp())}"
        payload = {"job_id": job_id}

        logger.info(
            f"Planner → Reporter: invoking agentcore"
            f" | arn={agent_arn} | session_id={session_id}"
        )
        logger.info(f"Planner → Reporter: payload={payload}")

        start_ts = datetime.now()
        add_job_progress(db, job_id, f"Invoking Reporter agent", "planner")
        result = await invoke_agent_with_boto3(agent_arn, session_id, payload)
        duration = (datetime.now() - start_ts).total_seconds()

        preview = (result or "").strip()
        if len(preview) > 300:
            preview = preview[:300] + "..."
        logger.info(f"Planner ← Reporter: completed in {duration:.1f}s | result='{preview}'")
        add_job_progress(db, job_id, f"Reporter completed in {duration:.1f}s", "planner")

        return f"Reporter agent completed: {result}"

    except Exception as e:
        db = Database()
        add_job_progress(db, job_id, f"Reporter failed: {str(e)}", "planner")
        logger.error(f"Planner ← Reporter: error invoking reporter agent: {e}", exc_info=True)
        return f"Reporter agent failed: {str(e)}"

@tool
async def invoke_charter_agent(job_id: str) -> str:
    """
    Invoke the Chart Maker agent to create portfolio visualizations.
    
    Args:
        job_id: The job ID for the analysis
        
    Returns:
        Chart creation result message
    """
    try:
        # Get database instance  
        db = Database()
        
        agent_arn = get_agent_arn("charter")
        if not agent_arn:
            add_job_progress(db, job_id, "Error: Could not find Charter agent ARN", "planner")
            return "Error: Could not find Charter agent ARN"

        session_id = f"planner-{job_id}-{int(datetime.now().timestamp())}"
        # Charter benefits from portfolio_data; planner can optionally load it later
        payload = {"job_id": job_id}

        logger.info(
            f"Planner → Charter: invoking agentcore"
            f" | arn={agent_arn} | session_id={session_id}"
        )
        logger.info(f"Planner → Charter: payload={payload}")

        start_ts = datetime.now()
        add_job_progress(db, job_id, f"Invoking Charter agent", "planner")
        result = await invoke_agent_with_boto3(agent_arn, session_id, payload)
        duration = (datetime.now() - start_ts).total_seconds()

        preview = (result or "").strip()
        if len(preview) > 300:
            preview = preview[:300] + "..."
        logger.info(f"Planner ← Charter: completed in {duration:.1f}s | result='{preview}'")
        add_job_progress(db, job_id, f"Charter completed in {duration:.1f}s", "planner")

        return f"Charter agent completed: {result}"

    except Exception as e:
        db = Database()
        add_job_progress(db, job_id, f"Charter failed: {str(e)}", "planner")
        logger.error(f"Planner ← Charter: error invoking charter agent: {e}", exc_info=True)
        return f"Charter agent failed: {str(e)}"

@tool
async def invoke_retirement_agent(job_id: str) -> str:
    """
    Invoke the Retirement Specialist agent for retirement projections.
    
    Args:
        job_id: The job ID for the analysis
        
    Returns:
        Retirement analysis result message
    """
    try:
        # Get database instance
        db = Database()
        
        agent_arn = get_agent_arn("retirement")
        if not agent_arn:
            add_job_progress(db, job_id, "Error: Could not find Retirement agent ARN", "planner")
            return "Error: Could not find Retirement agent ARN"

        session_id = f"planner-{job_id}-{int(datetime.now().timestamp())}"
        payload = {"job_id": job_id}

        logger.info(
            f"Planner → Retirement: invoking agentcore"
            f" | arn={agent_arn} | session_id={session_id}"
        )
        logger.info(f"Planner → Retirement: payload={payload}")

        start_ts = datetime.now()
        add_job_progress(db, job_id, f"Invoking Retirement agent", "planner")
        result = await invoke_agent_with_boto3(agent_arn, session_id, payload)
        duration = (datetime.now() - start_ts).total_seconds()

        preview = (result or "").strip()
        if len(preview) > 300:
            preview = preview[:300] + "..."
        logger.info(f"Planner ← Retirement: completed in {duration:.1f}s | result='{preview}'")
        add_job_progress(db, job_id, f"Retirement completed in {duration:.1f}s", "planner")

        return f"Retirement agent completed: {result}"

    except Exception as e:
        db = Database()
        add_job_progress(db, job_id, f"Retirement failed: {str(e)}", "planner")
        logger.error(f"Planner ← Retirement: error invoking retirement agent: {e}", exc_info=True)
        return f"Retirement agent failed: {str(e)}"

@tool
async def invoke_tagger_agent(instruments: list) -> str:
    """
    Invoke the Tagger agent to classify financial instruments.
    
    Args:
        instruments: List of instruments to classify
        
    Returns:
        Classification result message
    """
    try:
        agent_arn = get_agent_arn("tagger")
        if not agent_arn:
            return "Error: Could not find Tagger agent ARN"

        session_id = f"planner-tagger-{int(datetime.now().timestamp())}"
        # Avoid overly long log lines — summarize instruments
        symbols = [i.get('symbol') or i for i in instruments]
        summary = symbols[:10]
        more = f" +{len(symbols)-10} more" if len(symbols) > 10 else ""
        payload = {"instruments": instruments}

        logger.info(
            f"Planner → Tagger: invoking agentcore"
            f" | arn={agent_arn} | session_id={session_id} | instruments={summary}{more}"
        )

        start_ts = datetime.now()
        result = await invoke_agent_with_boto3(agent_arn, session_id, payload)
        duration = (datetime.now() - start_ts).total_seconds()

        preview = (result or "").strip()
        if len(preview) > 300:
            preview = preview[:300] + "..."
        logger.info(f"Planner ← Tagger: completed in {duration:.1f}s | result='{preview}'")

        return f"Tagger agent completed: {result}"

    except Exception as e:
        logger.error(f"Planner ← Tagger: error invoking tagger agent: {e}", exc_info=True)
        return f"Tagger agent failed: {str(e)}"

async def handle_missing_instruments(job_id: str, db: Database) -> None:
    """
    Check for and tag any instruments missing allocation data.
    This is done automatically before the agent runs.
    """
    logger.info("Planner: Checking for instruments missing allocation data...")

    # Get job and portfolio data
    job = db.jobs.find_by_id(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    user_id = job["clerk_user_id"]
    accounts = db.accounts.find_by_user(user_id)

    missing = []
    for account in accounts:
        positions = db.positions.find_by_account(account["id"])
        for position in positions:
            instrument = db.instruments.find_by_symbol(position["symbol"])
            if instrument:
                has_allocations = bool(
                    instrument.get("allocation_regions")
                    and instrument.get("allocation_sectors")
                    and instrument.get("allocation_asset_class")
                )
                if not has_allocations:
                    missing.append(
                        {"symbol": position["symbol"], "name": instrument.get("name", "")}
                    )
            else:
                missing.append({"symbol": position["symbol"], "name": ""})

    if missing:
        logger.info(
            f"Planner: Found {len(missing)} instruments needing classification: {[m['symbol'] for m in missing]}"
        )
        # Use the tagger tool to classify missing instruments
        tagger_result = await invoke_tagger_agent(missing)
        logger.info(f"Planner: Tagger tool returned: {(tagger_result or '')[:300]}{'...' if tagger_result and len(tagger_result)>300 else ''}")
    else:
        logger.info("Planner: All instruments have allocation data")

async def create_agent_and_run(job_id: str) -> str:
    """
    Create and run the orchestrator agent for portfolio analysis coordination.
    
    Args:
        job_id: The portfolio analysis job ID
        
    Returns:
        Final orchestration result
    """
    try:
        # Initialize database and set status
        db = Database()
        db.jobs.update_status(job_id, 'running')

        # Handle missing instruments first (non-agent pre-processing)
        logger.info(f"Planner: Starting pre-processing for job {job_id}")
        await handle_missing_instruments(job_id, db)
        logger.info("Planner: Pre-processing completed")

        # Load portfolio summary (just statistics, not full data)
        portfolio_summary = await asyncio.to_thread(load_portfolio_summary, job_id, db)
        logger.info(
            "Planner: Portfolio summary loaded "
            f"| accounts={portfolio_summary['num_accounts']} "
            f"| positions={portfolio_summary['num_positions']} "
            f"| total_value=${portfolio_summary['total_value']:.2f}"
        )

        # Get model configuration and create model
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-haiku-20240307-v1:0")
        logger.info(f"Planner: Using Bedrock model_id={model_id}")
        model = BedrockModel(model_id=model_id)

        # Deterministic kickoff: invoke core agents based on summary, independent of LLM tool-calling
        logger.info("Planner: Deterministic kickoff of downstream agents")
        try:
            # Always reporter if positions > 0
            if portfolio_summary.get('num_positions', 0) > 0:
                logger.info("Planner: Invoking Reporter (positions > 0)")
                await invoke_reporter_agent(job_id)
            else:
                logger.info("Planner: Skipping Reporter (no positions)")

            # Charter if at least 2 positions
            if portfolio_summary.get('num_positions', 0) >= 2:
                logger.info("Planner: Invoking Charter (positions >= 2)")
                await invoke_charter_agent(job_id)
            else:
                logger.info("Planner: Skipping Charter (positions < 2)")

            # Retirement if years_until_retirement > 0
            if portfolio_summary.get('years_until_retirement', 0) > 0:
                logger.info("Planner: Invoking Retirement (years_until_retirement > 0)")
                await invoke_retirement_agent(job_id)
            else:
                logger.info("Planner: Skipping Retirement (years_until_retirement <= 0)")
        except Exception as e:
            logger.error(f"Planner: Error during deterministic kickoff: {e}", exc_info=True)

        # Create the orchestrator agent instructions (still run LLM to summarize)
        instructions = f"""You are the Financial Planner Orchestrator. Your job is to coordinate portfolio analysis by calling specialized agents.

Portfolio Summary:
- Total positions: {portfolio_summary['num_positions']}
- Number of accounts: {portfolio_summary['num_accounts']}
- Years until retirement: {portfolio_summary['years_until_retirement']}
- Total portfolio value: ${portfolio_summary['total_value']:,.2f}

Your available tools:
1. invoke_reporter_agent: Generate comprehensive portfolio analysis narrative
2. invoke_charter_agent: Create portfolio visualization charts
3. invoke_retirement_agent: Calculate retirement projections and scenarios
4. invoke_tagger_agent: Classify financial instruments (usually done automatically)

Orchestration Steps:
1. Always call invoke_reporter_agent first if there are positions > 0
2. Call invoke_charter_agent if there are positions >= 2 (charts need multiple data points)
3. Call invoke_retirement_agent if retirement planning is needed (years_until_retirement > 0)
4. Coordinate the analysis and provide a final summary

Call each agent with the job_id: {job_id}

Begin the orchestration process now."""

        # Create agent
        agent = Agent(
            model=model,
            system_prompt=instructions,
            tools=[
                invoke_reporter_agent,
                invoke_charter_agent,
                invoke_retirement_agent,
                invoke_tagger_agent,
            ],
        )

    # Create task and run (optional summarization)
        task = f"Begin comprehensive portfolio analysis orchestration for job {job_id}"
        logger.info("Planner: Starting agent orchestration run...")
        result = agent(task)
        logger.info("Planner: Agent orchestration run completed")

        # Extract the text content from the AgentResult
        response = result.text if hasattr(result, 'text') else str(result)
        logger.info(
            "Planner: Final orchestrator response (truncated): "
            f"'{(response or '')[:300]}{'...' if response and len(response)>300 else ''}'"
        )

        # Mark job as completed after all agents finish
        db.jobs.update_status(job_id, "completed")
        logger.info(f"Planner: Job {job_id} completed successfully")

        return response

    except Exception as e:
        logger.error(f"Error in orchestration: {e}", exc_info=True)
        if 'db' in locals():
            db.jobs.update_status(job_id, 'failed', error_message=str(e))
        raise


app = BedrockAgentCoreApp()


@app.entrypoint
def planner_agent(payload):
    """Main entry point for the planner orchestrator agent."""
    try:
        logger.info(f"Planner Agent invoked with payload: {json.dumps(payload)[:500]}")

        # Parse the payload
        job_id = payload.get("job_id")
        if not job_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'job_id is required'})
            }

        # Process the orchestration in a single async context
        result = asyncio.run(create_agent_and_run(job_id))

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'message': f'Orchestration completed for job {job_id}',
                'final_output': result
            })
        }

    except Exception as e:
        logger.error(f"Planner agent error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


if __name__ == "__main__":
    app.run()