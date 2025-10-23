"""
SQS to AgentCore Bridge Lambda Function

This Lambda function receives SQS messages and invokes the AgentCore planner agent.
"""

import json
import logging
import boto3
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize boto3 client for AgentCore
bedrock_agentcore = boto3.client('bedrock-agentcore')
ssm = boto3.client('ssm')

def get_planner_agent_arn() -> str:
    """Get the planner agent ARN from SSM Parameter Store."""
    try:
        response = ssm.get_parameter(Name='/agents/planner_agent_arn')
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Failed to get planner agent ARN: {e}")
        raise

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Handle SQS messages and invoke AgentCore planner agent.
    
    Expected SQS message body: {"job_id": "uuid"}
    """
    try:
        logger.info(f"SQS Orchestrator invoked with event: {json.dumps(event)}")
        
        # Get planner agent ARN
        planner_arn = get_planner_agent_arn()
        logger.info(f"Using planner agent ARN: {planner_arn}")
        
        successful_jobs = []
        failed_jobs = []
        
        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse job_id from SQS message
                message_body = record['body']
                logger.info(f"Processing message: {message_body}")
                
                # Parse JSON if needed
                if isinstance(message_body, str):
                    try:
                        body_data = json.loads(message_body)
                        job_id = body_data.get('job_id', message_body)
                    except json.JSONDecodeError:
                        job_id = message_body
                else:
                    job_id = message_body
                
                logger.info(f"Extracted job_id: {job_id}")
                
                # Create payload for AgentCore
                payload = {
                    "job_id": job_id
                }
                
                # Convert payload to JSON string (bedrock agentcore expects JSON string, not base64)
                payload_json = json.dumps(payload)
                
                logger.info(f"Invoking planner agent for job: {job_id} with payload: {payload_json}")
                
                # Invoke AgentCore planner agent
                response = bedrock_agentcore.invoke_agent_runtime(
                    agentRuntimeArn=planner_arn,
                    payload=payload_json
                )
                
                logger.info(f"Planner agent invoked successfully for job: {job_id}")
                successful_jobs.append(job_id)
                
            except Exception as e:
                logger.error(f"Failed to process record {record.get('messageId', 'unknown')}: {e}")
                failed_jobs.append({
                    'messageId': record.get('messageId', 'unknown'),
                    'error': str(e)
                })
        
        # Return results
        result = {
            'statusCode': 200 if not failed_jobs else 207,  # 207 = Multi-Status
            'body': json.dumps({
                'successful_jobs': successful_jobs,
                'failed_jobs': failed_jobs,
                'total_processed': len(event.get('Records', [])),
                'success_count': len(successful_jobs),
                'failure_count': len(failed_jobs)
            })
        }
        
        logger.info(f"SQS Orchestrator completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Fatal error in SQS Orchestrator: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'successful_jobs': [],
                'failed_jobs': []
            })
        }

# For local testing
if __name__ == "__main__":
    # Test with a sample SQS event
    test_event = {
        "Records": [
            {
                "messageId": "test-message-1",
                "body": '{"job_id": "test-job-uuid-123"}'
            }
        ]
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))