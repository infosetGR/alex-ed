#!/usr/bin/env python3
"""
Save environment variables from .env file to AWS Systems Manager Parameter Store.
This script is called by Terraform when the .env file changes.
"""

import sys
import os

# Add backend directory to Python path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from utils import save_env_to_ssm

def main():
    """Main function to save environment variables to SSM."""
    print('🔧 Saving environment variables from .env to AWS Systems Manager Parameter Store...')
    print('=' * 70)

    # Path to the .env file (two directories up from terraform/6_agents)
    env_file_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    
    # Get AWS region from environment variable (set by Terraform)
    region = os.getenv('AWS_REGION', os.getenv('DEFAULT_AWS_REGION', 'us-east-1'))
    
    try:
        summary = save_env_to_ssm(
            env_file_path=env_file_path,
            prefix='/alex/env/',
            region=region
        )
        
        print()
        print('=' * 70)
        print('📊 SUMMARY')
        print('=' * 70)
        print(f'✅ Successfully saved: {summary["saved_count"]} parameters')
        print(f'⚠️  Skipped: {summary["skipped_count"]} parameters')
        print(f'🏷️  Prefix used: {summary["prefix"]}')
        print(f'🌍 Region: {summary["region"]}')
        
        if summary['saved_parameters']:
            print()
            print('✅ SAVED PARAMETERS:')
            for key, param_name in summary['saved_parameters'].items():
                print(f'   {key} → {param_name}')
        
        if summary['skipped_parameters']:
            print()
            print('⚠️  SKIPPED PARAMETERS:')
            for key, reason in summary['skipped_parameters'].items():
                print(f'   {key}: {reason}')
        
        print()
        print('🎉 Environment variables have been saved to SSM Parameter Store!')
        print('   Your agents will now be able to load these variables automatically.')
        
        return 0
        
    except Exception as e:
        print(f'❌ Error saving environment variables to SSM: {e}')
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)