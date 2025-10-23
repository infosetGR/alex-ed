terraform {
  required_version = ">= 1.5"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Using local backend - state will be stored in terraform.tfstate in this directory
  # This is automatically gitignored for security
}

provider "aws" {
  region = var.aws_region
}

# Data source for current caller identity
data "aws_caller_identity" "current" {}

# ========================================
# Environment Variables to SSM
# ========================================

# Resource to save environment variables to SSM when .env file changes
resource "null_resource" "save_env_to_ssm" {
  # Trigger when .env file changes
  triggers = {
    env_file_hash = filemd5("../../.env")
  }
  
  provisioner "local-exec" {
    command = "uv run save_env_to_ssm.py"
    
    working_dir = path.module
    
    environment = {
      AWS_REGION = var.aws_region
    }
  }

  depends_on = []
  
  # Add lifecycle to ensure this runs before agent deployments
  lifecycle {
    create_before_destroy = true
  }
}

# ========================================
# SQS Queue for Async Job Processing
# ========================================

resource "aws_sqs_queue" "analysis_jobs" {
  name                       = "alex-analysis-jobs"
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400  # 1 day
  receive_wait_time_seconds = 10     # Long polling
  visibility_timeout_seconds = 910   # 15 minutes + 10 seconds buffer (matches Planner Lambda timeout)
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.analysis_jobs_dlq.arn
    maxReceiveCount     = 3
  })
  
  tags = {
    Project = "alex"
    Part    = "6"
  }
}

resource "aws_sqs_queue" "analysis_jobs_dlq" {
  name = "alex-analysis-jobs-dlq"
  
  tags = {
    Project = "alex"
    Part    = "6"
  }
}

# ========================================
# IAM Role for Lambda Functions
# ========================================

resource "aws_iam_role" "lambda_agents_role" {
  name = "alex-lambda-agents-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Project = "alex"
    Part    = "6"
  }
}

# IAM policy for Lambda agents
resource "aws_iam_role_policy" "lambda_agents_policy" {
  name = "alex-lambda-agents-policy"
  role = aws_iam_role.lambda_agents_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      # SQS access for orchestrator
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.analysis_jobs.arn
      },
      # Lambda invocation for orchestrator to call other agents
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:alex-*"
      },
      # Aurora Data API access
      {
        Effect = "Allow"
        Action = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction"
        ]
        # Resource = var.aurora_cluster_arn
        Resource = "*"
      },
      # Secrets Manager for database credentials
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      },
      # S3 Vectors access for all agents
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.vector_bucket}",
          "arn:aws:s3:::${var.vector_bucket}/*"
        ]
      },
      # S3 Vectors API access for all agents
      {
        Effect = "Allow"
        Action = [
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors"
        ]
        Resource = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket}/index/*"
      },
      # SageMaker endpoint access for reporter agent
      {
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint"
        ]
        Resource = "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.sagemaker_endpoint}"
      },
      # Bedrock access for all agents
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.bedrock_region}::foundation-model/*",
          "arn:aws:bedrock:${var.bedrock_region}:*:inference-profile/*"
        ]
      },
      # Bedrock AgentCore access for SQS orchestrator
      {
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:runtime/*"
        ]
      },
      # SSM Parameter Store access for agent ARNs and environment variables
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach basic Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_agents_basic" {
  role       = aws_iam_role.lambda_agents_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ========================================
# SQS to AgentCore Bridge Lambda
# ========================================

# Package the SQS orchestrator Lambda
data "archive_file" "sqs_orchestrator" {
  type        = "zip"
  source_file = "${path.module}/../../backend/sqs_orchestrator/lambda_handler.py"
  output_path = "${path.module}/sqs_orchestrator.zip"
}

# SQS to AgentCore Bridge Lambda Function
resource "aws_lambda_function" "sqs_orchestrator" {
  function_name = "alex-sqs-orchestrator"
  role          = aws_iam_role.lambda_agents_role.arn

  filename         = data.archive_file.sqs_orchestrator.output_path
  source_code_hash = data.archive_file.sqs_orchestrator.output_base64sha256

  handler     = "lambda_handler.lambda_handler"
  runtime     = "python3.12"
  timeout     = 60   # 1 minute should be enough to invoke AgentCore
  memory_size = 256  # Minimal memory needed

  environment {
    variables = {
      DEFAULT_AWS_REGION = var.aws_region
    }
  }

  tags = {
    Project = "alex"
    Part    = "6"
    Purpose = "sqs-agentcore-bridge"
  }
}

# SQS trigger for the orchestrator Lambda
resource "aws_lambda_event_source_mapping" "sqs_orchestrator" {
  event_source_arn = aws_sqs_queue.analysis_jobs.arn
  function_name    = aws_lambda_function.sqs_orchestrator.arn
  batch_size       = 1  # Process one message at a time
  
  depends_on = [aws_lambda_function.sqs_orchestrator]
}

# Add CloudWatch Logs for the SQS orchestrator
resource "aws_cloudwatch_log_group" "sqs_orchestrator_logs" {
  name              = "/aws/lambda/alex-sqs-orchestrator"
  retention_in_days = 7
  
  tags = {
    Project = "alex"
    Part    = "6"
  }
}

# # ========================================
# # S3 Bucket for Lambda Deployments
# # ========================================

# # S3 bucket for Lambda packages (packages > 50MB must use S3)
# resource "aws_s3_bucket" "lambda_packages" {
#   bucket = "alex-lambda-packages-${data.aws_caller_identity.current.account_id}"
  
#   tags = {
#     Project = "alex"
#     Part    = "6"
#   }
# }

# # Upload Lambda packages to S3
# resource "aws_s3_object" "lambda_packages" {
#   for_each = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  
#   bucket = aws_s3_bucket.lambda_packages.id
#   key    = "${each.key}/${each.key}_lambda.zip"
#   source = "${path.module}/../../backend/${each.key}/${each.key}_lambda.zip"
#   etag   = fileexists("${path.module}/../../backend/${each.key}/${each.key}_lambda.zip") ? filemd5("${path.module}/../../backend/${each.key}/${each.key}_lambda.zip") : null
  
#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = each.key
#   }
# }

# # ========================================
# # Lambda Functions for Each Agent
# # ========================================

# # Planner (Orchestrator) Lambda
# resource "aws_lambda_function" "planner" {
#   function_name = "alex-planner"
#   role          = aws_iam_role.lambda_agents_role.arn
  
#   # Using S3 for deployment package (>50MB)
#   s3_bucket        = aws_s3_bucket.lambda_packages.id
#   s3_key           = aws_s3_object.lambda_packages["planner"].key
#   source_code_hash = fileexists("${path.module}/../../backend/planner/planner_lambda.zip") ? filebase64sha256("${path.module}/../../backend/planner/planner_lambda.zip") : null
  
#   handler     = "lambda_handler.lambda_handler"
#   runtime     = "python3.12"
#   timeout     = 900  # 15 minutes for planner
#   memory_size = 2048  # 2GB for planner
  
#   environment {
#     variables = {
#       AURORA_CLUSTER_ARN = var.aurora_cluster_arn
#       AURORA_SECRET_ARN  = var.aurora_secret_arn
#       DATABASE_NAME      = "alex"
#       VECTOR_BUCKET      = var.vector_bucket
#       BEDROCK_MODEL_ID   = var.bedrock_model_id
#       BEDROCK_REGION     = var.bedrock_region
#       DEFAULT_AWS_REGION = var.aws_region
#       SAGEMAKER_ENDPOINT = var.sagemaker_endpoint
#       POLYGON_API_KEY    = var.polygon_api_key
#       POLYGON_PLAN       = var.polygon_plan
#       # LangFuse observability (optional)
#       LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
#       LANGFUSE_SECRET_KEY = var.langfuse_secret_key
#       LANGFUSE_HOST       = var.langfuse_host
#       OPENAI_API_KEY      = var.openai_api_key
#     }
#   }

#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = "orchestrator"
#   }
  
#   depends_on = [aws_s3_object.lambda_packages["planner"]]
# }

# SQS trigger for Planner
# Note: SQS will be processed by AgentCore agents, not Lambda functions
# The planner agent will poll SQS directly when invoked
# resource "aws_lambda_event_source_mapping" "planner_sqs" {
#   event_source_arn = aws_sqs_queue.analysis_jobs.arn
#   function_name    = aws_lambda_function.planner.arn
#   batch_size       = 1
# }

# # Tagger Lambda
# resource "aws_lambda_function" "tagger" {
#   function_name = "alex-tagger"
#   role          = aws_iam_role.lambda_agents_role.arn

#   # Using S3 for deployment package (>50MB)
#   s3_bucket        = aws_s3_bucket.lambda_packages.id
#   s3_key           = aws_s3_object.lambda_packages["tagger"].key
#   source_code_hash = fileexists("${path.module}/../../backend/tagger/tagger_lambda.zip") ? filebase64sha256("${path.module}/../../backend/tagger/tagger_lambda.zip") : null

#   handler     = "lambda_handler.lambda_handler"
#   runtime     = "python3.12"
#   timeout     = 300  # 5 minutes for tagger
#   memory_size = 1024

#   environment {
#     variables = {
#       AURORA_CLUSTER_ARN = var.aurora_cluster_arn
#       AURORA_SECRET_ARN  = var.aurora_secret_arn
#       DATABASE_NAME      = "alex"
#       BEDROCK_MODEL_ID   = var.bedrock_model_id
#       BEDROCK_REGION     = var.bedrock_region
#       DEFAULT_AWS_REGION = var.aws_region
#       # LangFuse observability (optional)
#       LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
#       LANGFUSE_SECRET_KEY = var.langfuse_secret_key
#       LANGFUSE_HOST       = var.langfuse_host
#       OPENAI_API_KEY      = var.openai_api_key
#     }
#   }
  
#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = "tagger"
#   }
  
#   depends_on = [aws_s3_object.lambda_packages["tagger"]]
# }

# # Reporter Lambda
# resource "aws_lambda_function" "reporter" {
#   function_name = "alex-reporter"
#   role          = aws_iam_role.lambda_agents_role.arn
  
#   # Using S3 for deployment package (>50MB)
#   s3_bucket        = aws_s3_bucket.lambda_packages.id
#   s3_key           = aws_s3_object.lambda_packages["reporter"].key
#   source_code_hash = fileexists("${path.module}/../../backend/reporter/reporter_lambda.zip") ? filebase64sha256("${path.module}/../../backend/reporter/reporter_lambda.zip") : null
  
#   handler     = "lambda_handler.lambda_handler"
#   runtime     = "python3.12"
#   timeout     = 300  # 5 minutes for reporter agent
#   memory_size = 1024
  
#   environment {
#     variables = {
#       AURORA_CLUSTER_ARN = var.aurora_cluster_arn
#       AURORA_SECRET_ARN  = var.aurora_secret_arn
#       DATABASE_NAME      = "alex"
#       BEDROCK_MODEL_ID   = var.bedrock_model_id
#       BEDROCK_REGION     = var.bedrock_region
#       DEFAULT_AWS_REGION = var.aws_region
#       SAGEMAKER_ENDPOINT = var.sagemaker_endpoint
#       # LangFuse observability (optional)
#       LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
#       LANGFUSE_SECRET_KEY = var.langfuse_secret_key
#       LANGFUSE_HOST       = var.langfuse_host
#       OPENAI_API_KEY      = var.openai_api_key
#     }
#   }

#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = "reporter"
#   }
  
#   depends_on = [aws_s3_object.lambda_packages["reporter"]]
# }

# # Charter Lambda
# resource "aws_lambda_function" "charter" {
#   function_name = "alex-charter"
#   role          = aws_iam_role.lambda_agents_role.arn
  
#   # Using S3 for deployment package (>50MB)
#   s3_bucket        = aws_s3_bucket.lambda_packages.id
#   s3_key           = aws_s3_object.lambda_packages["charter"].key
#   source_code_hash = fileexists("${path.module}/../../backend/charter/charter_lambda.zip") ? filebase64sha256("${path.module}/../../backend/charter/charter_lambda.zip") : null
  
#   handler     = "lambda_handler.lambda_handler"
#   runtime     = "python3.12"
#   timeout     = 300  # 5 minutes for charter agent
#   memory_size = 1024
  
#   environment {
#     variables = {
#       AURORA_CLUSTER_ARN = var.aurora_cluster_arn
#       AURORA_SECRET_ARN  = var.aurora_secret_arn
#       DATABASE_NAME      = "alex"
#       BEDROCK_MODEL_ID   = var.bedrock_model_id
#       BEDROCK_REGION     = var.bedrock_region
#       DEFAULT_AWS_REGION = var.aws_region
#       # LangFuse observability (optional)
#       LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
#       LANGFUSE_SECRET_KEY = var.langfuse_secret_key
#       LANGFUSE_HOST       = var.langfuse_host
#       OPENAI_API_KEY      = var.openai_api_key
#     }
#   }

#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = "charter"
#   }
  
#   depends_on = [aws_s3_object.lambda_packages["charter"]]
# }

# # Retirement Lambda
# resource "aws_lambda_function" "retirement" {
#   function_name = "alex-retirement"
#   role          = aws_iam_role.lambda_agents_role.arn
  
#   # Using S3 for deployment package (>50MB)
#   s3_bucket        = aws_s3_bucket.lambda_packages.id
#   s3_key           = aws_s3_object.lambda_packages["retirement"].key
#   source_code_hash = fileexists("${path.module}/../../backend/retirement/retirement_lambda.zip") ? filebase64sha256("${path.module}/../../backend/retirement/retirement_lambda.zip") : null
  
#   handler     = "lambda_handler.lambda_handler"
#   runtime     = "python3.12"
#   timeout     = 300  # 5 minutes for retirement agent
#   memory_size = 1024
  
#   environment {
#     variables = {
#       AURORA_CLUSTER_ARN = var.aurora_cluster_arn
#       AURORA_SECRET_ARN  = var.aurora_secret_arn
#       DATABASE_NAME      = "alex"
#       BEDROCK_MODEL_ID   = var.bedrock_model_id
#       BEDROCK_REGION     = var.bedrock_region
#       DEFAULT_AWS_REGION = var.aws_region
#       # LangFuse observability (optional)
#       LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
#       LANGFUSE_SECRET_KEY = var.langfuse_secret_key
#       LANGFUSE_HOST       = var.langfuse_host
#       OPENAI_API_KEY      = var.openai_api_key
#     }
#   }

#   tags = {
#     Project = "alex"
#     Part    = "6"
#     Agent   = "retirement"
#   }
  
#   depends_on = [aws_s3_object.lambda_packages["retirement"]]
# }

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "agent_logs" {
  for_each = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  
  name              = "/aws/lambda/alex-${each.key}"
  retention_in_days = 7
  
  tags = {
    Project = "alex"
    Part    = "6"
    Agent   = each.key
  }
}

# ========================================
# Deploy Agents using OpenAI Agents SDK
# ========================================

# Deploy agents using the deploy_agents.py script



resource "null_resource" "deploy_agents" {
  for_each = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  
  triggers = {
    # Redeploy if agent.py changes
    agent_file_hash = filemd5("${path.module}/../../backend/${each.key}/agent.py")
    # Redeploy if pyproject.toml changes (dependencies)
    pyproject_hash = filemd5("${path.module}/../../backend/${each.key}/pyproject.toml")
    # Redeploy if deploy script changes
    deploy_script_hash = filemd5("${path.module}/deploy_agents.py")
    # Force redeploy to update IAM permissions
    force_redeploy = "2025-10-22T21:00:00Z"
  }
  
  provisioner "local-exec" {
    command = "cd ${path.module} && uv run deploy_agents.py ${each.key}"
    
    environment = {
      DEFAULT_AWS_REGION = var.aws_region
      BEDROCK_REGION     = var.bedrock_region
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      # AURORA_CLUSTER_ARN = var.aurora_cluster_arn
      # AURORA_SECRET_ARN  = var.aurora_secret_arn
      # DATABASE_NAME      = "alex"
      SQLALCHEMY_DATABASE_URI = var.sqlalchemy_database_uri
      VECTOR_BUCKET      = var.vector_bucket
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint
      POLYGON_API_KEY    = var.polygon_api_key
      POLYGON_PLAN       = var.polygon_plan
      LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
      LANGFUSE_SECRET_KEY = var.langfuse_secret_key
      LANGFUSE_HOST       = var.langfuse_host
      OPENAI_API_KEY      = var.openai_api_key
    }
  }
  
  # Clean up on destroy (optional)
  provisioner "local-exec" {
    when    = destroy
    command =  "cd ${path.module} && uv run destroy_agents.py ${each.key}"
  }
  
  depends_on = [
    aws_iam_role.lambda_agents_role,
    null_resource.save_env_to_ssm
  ]
}

# # Data source to retrieve agent ARNs from SSM Parameter Store
# Data source to retrieve agent ARNs from SSM Parameter Store
data "aws_ssm_parameter" "agent_arns" {
  for_each = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  
  name = "/agents/${each.key}_agent_arn"
  
  depends_on = [null_resource.deploy_agents]
}

# ========================================
# AgentCore IAM Permissions
# ========================================

# IAM policy for AgentCore roles to allow cross-agent communication
resource "aws_iam_role_policy" "agentcore_cross_invoke_policy" {
  for_each = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  
  name = "agentcore-${each.key}-cross-invoke-policy"
  role = "agentcore-${each.key}-role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Allow invoking other AgentCore runtimes
      {
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:runtime/*"
        ]
      },
      # Aurora Data API access
      {
        Effect = "Allow"
        Action = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction"
        ]
        Resource = "*"
      },
      # Secrets Manager for database credentials
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      },
      # S3 Vectors access
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.vector_bucket}",
          "arn:aws:s3:::${var.vector_bucket}/*"
        ]
      },
      # S3 Vectors API access
      {
        Effect = "Allow"
        Action = [
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors"
        ]
        Resource = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket}/index/*"
      },
      # SageMaker endpoint access
      {
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint"
        ]
        Resource = "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.sagemaker_endpoint}"
      },
      # Bedrock model access
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.bedrock_region}::foundation-model/*",
          "arn:aws:bedrock:${var.bedrock_region}:*:inference-profile/*"
        ]
      },
      # SSM Parameter Store access
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = "*"
      },
      # CloudWatch Logs (for debugging)
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })

  depends_on = [null_resource.deploy_agents]
}