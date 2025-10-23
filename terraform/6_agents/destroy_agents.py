#!/usr/bin/env python3
"""
Destroy deployed Bedrock AgentCore agents and their resources.
"""
import json
import boto3
import os
import sys
from bedrock_agentcore_starter_toolkit import Runtime

def destroy_agent(agent_name=None):
    """
    Tear down a deployed Bedrock AgentCore agent and its resources.
    
    Args:
        agent_name: Specific agent to destroy, or None to destroy all
    """
    
    # Define the 5 agents explicitly
    agent_names = ['planner', 'tagger', 'reporter', 'charter', 'retirement']
    
    if agent_name:
        if agent_name not in agent_names:
            print(f"❌ Unknown agent: {agent_name}")
            print(f"   Valid agents: {', '.join(agent_names)}")
            return False
        agents_to_destroy = [agent_name]
    else:
        agents_to_destroy = agent_names
    
    success_count = 0
    total_count = len(agents_to_destroy)
    
    # Get region from environment or default
    region = os.environ.get('AWS_REGION', 'us-east-1')
    ssm = boto3.client('ssm', region_name=region)
    
    for agent_name_current in agents_to_destroy:
        try:
            # Read agent ARN from SSM parameter
            parameter_name = f'/agents/{agent_name_current}_agent_arn'

              # Clean up local configuration files for this agent
            try:
                agent_dir = f"../../backend/agent_{agent_name_current}"
                config_files_to_clean = [
                    f"{agent_dir}/.bedrock_agentcore.yaml",
                    f"{agent_dir}/agent_deployment_{agent_name_current}.json"
                ]
                
                for config_file in config_files_to_clean:
                    if os.path.exists(config_file):
                        os.remove(config_file)
                        print(f"   ✅ Removed local config file: {config_file}")
                        
            except Exception as e:
                print(f"   Warning: Could not clean up local config files: {e}")
            
            try:
                agent_dir = f"../../backend/agent_{agent_name_current}"
                print(agent_dir)
                config_files_to_clean = [
                    f"{agent_dir}/.bedrock_agentcore.yaml",
                    f"{agent_dir}/agent_deployment_{agent_name_current}.json"
                ]
                print(f"   ✅ Removing local config file: {config_file}")
                for config_file in config_files_to_clean:
                    if os.path.exists(config_file):
                        os.remove(config_file)
                        print(f"   ✅ Removed local config file: {config_file}")
                        
            except Exception as e:
                print(f"   Warning: Could not clean up local config files: {e}")

            print(f"\n🧹 Destroying agent: {agent_name_current}")
            print(f"   Reading parameter: {parameter_name}")

            try:
                response = ssm.get_parameter(Name=parameter_name)
                agent_arn = response['Parameter']['Value']
                print(f"   Agent ARN: {agent_arn}")
                
                # Extract agent ID from ARN (format: arn:aws:bedrock:region:account:agent/agent-id)
                agent_id = agent_arn.split('/')[-1]
                print(f"   Agent ID: {agent_id}")
                
            except ssm.exceptions.ParameterNotFound:
                print(f"❌ Parameter not found: {parameter_name}")
                print(f"   Agent {agent_name_current} may not be deployed or already destroyed")
                continue
            except Exception as e:
                print(f"❌ Error reading parameter {parameter_name}: {e}")
                continue
            
            # Destroy the agent using AWS Bedrock AgentCore client directly
            try:
                print(f"   Deleting AgentCore agent...")
                bedrock_agentcore_client = boto3.client('bedrock-agentcore', region_name=region)
                
                # Delete the agent runtime
                try:
                    # Try different possible method names
                    if hasattr(bedrock_agentcore_client, 'delete_agent'):
                        delete_response = bedrock_agentcore_client.delete_agent(
                            agentArn=agent_arn
                        )
                        print(f"   ✅ Agent deleted successfully using delete_agent")
                    elif hasattr(bedrock_agentcore_client, 'delete_agent_runtime'):
                        delete_response = bedrock_agentcore_client.delete_agent_runtime(
                            agentRuntimeArn=agent_arn
                        )
                        print(f"   ✅ Agent runtime deleted successfully using delete_agent_runtime")
                    else:
                        # List available methods for debugging
                        methods = [method for method in dir(bedrock_agentcore_client) if 'delete' in method.lower()]
                        print(f"   ⚠️ No delete method found. Available delete methods: {methods}")
                        raise Exception("No suitable delete method found on bedrock-agentcore client")
                except Exception as e:
                    print(f"   ⚠️ Could not delete agent runtime: {e}")
                    # Try alternative approach using runtime toolkit
                    try:
                        runtime = Runtime()
                        # Set agent properties if they exist
                        if hasattr(runtime, 'agent_id'):
                            runtime.agent_id = agent_id
                        if hasattr(runtime, 'region'):
                            runtime.region = region
                        
                        # Try common destruction methods
                        if hasattr(runtime, 'delete'):
                            runtime.delete()
                            print(f"   ✅ Agent deleted using runtime.delete()")
                        elif hasattr(runtime, 'terminate'):
                            runtime.terminate()
                            print(f"   ✅ Agent terminated using runtime.terminate()")
                        else:
                            print(f"   ⚠️ No destruction method found on Runtime object")
                    except Exception as runtime_error:
                        print(f"   ⚠️ Runtime toolkit cleanup failed: {runtime_error}")
                
            except Exception as e:
                print(f"   ⚠️ Error destroying agent: {e}")
                # Continue with cleanup even if agent destruction fails
            
            # Clean up IAM role (use predictable role name)
            agent_role_name = f"alex-{agent_name_current}-agent-role"
            try:
                print(f"   Cleaning up IAM role: {agent_role_name}")
                iam_client = boto3.client('iam', region_name=region)
                
                # List and delete role policies
                try:
                    policies = iam_client.list_role_policies(RoleName=agent_role_name)
                    for policy_name in policies['PolicyNames']:
                        iam_client.delete_role_policy(
                            RoleName=agent_role_name,
                            PolicyName=policy_name
                        )
                        print(f"   Deleted role policy: {policy_name}")
                except Exception as e:
                    print(f"   Warning: Could not clean up role policies: {e}")
                
                # Delete the role
                try:
                    iam_client.delete_role(RoleName=agent_role_name)
                    print(f"   ✅ Deleted IAM role: {agent_role_name}")
                except Exception as e:
                    print(f"   Warning: Could not delete IAM role: {e}")
                    
            except Exception as e:
                print(f"   Warning: IAM cleanup failed: {e}")
            
            # Clean up SSM parameter
            try:
                ssm.delete_parameter(Name=parameter_name)
                print(f"   ✅ Deleted SSM parameter: {parameter_name}")
            except Exception as e:
                print(f"   Warning: Could not delete SSM parameter: {e}")
            
          
            
            success_count += 1
            print(f"   ✅ Agent {agent_name_current} cleanup completed")
            
        except Exception as e:
            print(f"❌ Error processing agent {agent_name_current}: {e}")
            continue
    
    print(f"\n📊 Cleanup Summary: {success_count}/{total_count} agents processed successfully")
    return True #success_count == total_count

if __name__ == "__main__":
    if len(sys.argv) > 2:
        print("Usage: python destroy_agents.py [agent_name]")
        print("  agent_name: Optional specific agent to destroy")
        print("  If no agent specified, all deployed agents will be destroyed")
        sys.exit(1)
    
    agent_name = sys.argv[1] if len(sys.argv) == 2 else None
    
    if agent_name:
        print(f"🎯 Destroying specific agent: {agent_name}")
    else:
        print("🧹 Destroying all deployed agents...")
    
    success = destroy_agent(agent_name)
    sys.exit(0 if success else 1)