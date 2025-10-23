# AI Financial Advisor — AWS AI Agent Global Hackathon

Fotios Stathopoulos 
fotis@infoset.co
INFOSET


## Inspiration

 This is a great project  I started during an Udemy course by Edward Donner this summer. Its purpose is to help people understand their investments better, and also showcase the power of agentic AI on AWS. With the rise of AgentCore and Bedrock, I saw an opportunity to create a multi-agent financial advisor that is scalable, cost-effective, and easy to deploy beyond the course capstone project while at the same time preparing it as a reference architecture for future projects. Although AgentCore is still in its early days, this project showcase in an excellent way how it can serve a large scale enterprise multi-agent project of great complexity and strict requirements.

## What it does
- AWS-native, multi-agent financial advisor (Planner, Tagger, Reporter (with AgentCore browser tool), Charter, Retirement)
- Turns raw portfolios into personalized insights, reports, charts, and retirement projections
- Real-time market research via Bedrock tools, stored safely in a serverless backend

## How we built it
- Migrated orchestration and Agents (5 agents) to Amazon Bedrock (AgentCore) with a common agent template, shared tool schemas, and a registry pattern.
- Bedrock AgentCore runtime and tools for reasoning; SageMaker serverless embeddings + S3 Vectors for low-cost RAG
- Serverless by default: Lambda, SQS fan-out, Lambda API, Aurora Serverless v2 (Data API) or Postgres RDS
- Terraform-per-part IaC, uv+Docker packaging, CloudWatch observability

## Challenges we ran into
- Packaging and environmental variables for AgentCore
- Bedrock model access and cross-region inference profiles
- Structured outputs vs tool-calling trade-offs on Bedrock
- Keeping terraform.tfvars consistent across independent stacks

## Accomplishments that we’re proud of
- Seamless migration to Bedrock AgentCore with lower latency and higher reliability
- “New agent in minutes” process: pick model, attach tools, deploy via Terraform and common pattern.
- 90% vector cost savings using S3 Vectors over OpenSearch for RAG
- Parallel agent execution at scale with consistent guardrails and end-to-end tracing

## What we learned
- AgentCore standardizes orchestration and makes multi-agent expansion safe and fast
- Multi-region Bedrock patterns and inference profiles boost resilience
- Unified tracing/metrics accelerates debugging and iteration
- Templates + registry unlock repeatable, organization-wide agent development

## What’s next for AI Financial Advisor
- New agents: tax optimizer, anomaly/risk sentinel, compliance explainer
- Deeper Bedrock integrations: Knowledge Bases and Guardrails end-to-end
- FinOps and per-tenant scaling, SOC2-ready posture and security hardening
- Self-serve “agent kit” so teams can add domain agents in hours, not weeks

## Component Details

### 1. **Bedrock AgentCore**
- **Agents**: Planner, Tagger, Reporter with AgentCore Browser Tool, Charter, Retirement
- **Purpose**: Multi-agent orchestration platform
- **Runtime**: AWS Bedrock AgentCore with Nova Pro
- **Features**: Shared tool registry, parallel execution, standardized templates

### 2. **API Gateway**
- **Type**: REST API
- **Auth**: API Key authentication
- **Endpoints**: `/ingest` (POST)
- **Purpose**: Secure access to Lambda functions

### 3. **Lambda Functions**
- **alex-ingest**: Processes documents and stores embeddings
  - Runtime: Python 3.12
  - Memory: 512MB
  - Timeout: 30 seconds
- **alex-scheduler**: Triggers automated research
  - Runtime: Python 3.11
  - Memory: 128MB
  - Timeout: 150 seconds

### 4. **S3 Vectors** 
- **Purpose**: Native vector storage in S3
- **Features**: 
  - Sub-second similarity search
  - Automatic optimization
  - No minimum charges
  - Strongly consistent writes
- **Cost**: ~$30/month (vs ~$300/month for OpenSearch)
- **Scale**: Millions of vectors per index


### 5. **SageMaker Serverless**
- **Model**: sentence-transformers/all-MiniLM-L6-v2
- **Purpose**: Generate 384-dimensional embeddings
- **Memory**: 3GB
- **Concurrency**: 10 max

### 6. **EventBridge Scheduler**
- **Rule**: alex-research-schedule
- **Schedule**: Every 2 hours
- **Target**: alex-scheduler Lambda
- **Purpose**: Automated research generation

### 7. **AWS Bedrock**
- **Provider**: AWS Bedrock
- **Model**: OpenAI OSS 120B (open-weight model)
- **Region**: us-west-2 (model only available here)
- **Purpose**: Research generation and analysis
- **Features**: 128K context window, cross-region access
