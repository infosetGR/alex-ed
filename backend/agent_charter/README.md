# Chart Maker Agent (Bedrock AgentCore)

This is the Chart Maker Agent implementation using AWS Bedrock AgentCore. It analyzes portfolio data and generates visualization charts in JSON format for the Alex financial planning platform.

## Overview

The Chart Maker Agent creates 4-6 visualization charts that tell a compelling story about an investment portfolio. It analyzes portfolio composition and generates charts showing:

- Asset class distribution (equity vs bonds vs alternatives)
- Geographic exposure (North America, Europe, Asia, etc.)
- Sector breakdown (Technology, Healthcare, Financials, etc.)
- Account type allocation (401k, IRA, Taxable, etc.)
- Top holdings concentration (largest positions)
- Tax efficiency distribution

## Architecture

### Framework Migration
- **From**: OpenAI Agents SDK with LiteLLM
- **To**: Bedrock AgentCore with direct BedrockModel
- **Runtime**: AWS Bedrock native execution

### Key Components

1. **Agent Core (`agent.py`)**
   - Portfolio analysis and metrics calculation
   - Chart generation with structured JSON output
   - Direct Bedrock model integration
   - Error handling and validation

2. **Portfolio Analysis**
   - Calculates total portfolio value and allocations
   - Aggregates asset classes, regions, and sectors
   - Processes multiple account types and positions
   - Handles missing or null data gracefully

3. **Chart Generation**
   - Creates 4-6 charts with different perspectives
   - Outputs structured JSON with specific format
   - Includes chart metadata (title, type, description)
   - Uses proper color schemes for visualization

## Data Flow

```
Portfolio Data → Portfolio Analysis → Agent Processing → JSON Charts → Database Storage
```

### Input Format
```python
{
    "user_id": "user123",
    "job_id": "uuid",
    "accounts": [
        {
            "id": "acc1",
            "name": "401(k)",
            "type": "401k", 
            "cash_balance": 5000.0,
            "positions": [
                {
                    "symbol": "SPY",
                    "quantity": 100.0,
                    "instrument": {
                        "name": "SPDR S&P 500 ETF",
                        "current_price": 450.0,
                        "allocation_asset_class": {"equity": 100},
                        "allocation_regions": {"north_america": 100},
                        "allocation_sectors": {...}
                    }
                }
            ]
        }
    ]
}
```

### Output Format
```json
{
  "charts": [
    {
      "key": "asset_class_distribution",
      "title": "Asset Class Distribution", 
      "type": "pie",
      "description": "Shows the distribution of asset classes in the portfolio",
      "data": [
        {"name": "Equity", "value": 146365.00, "color": "#3B82F6"},
        {"name": "Fixed Income", "value": 29000.00, "color": "#10B981"}
      ]
    }
  ]
}
```

## Configuration

### Environment Variables
- `BEDROCK_MODEL_ID`: Model identifier (default: "us.amazon.nova-pro-v1:0")
- `BEDROCK_REGION`: AWS region (default: "us-west-2")

### Dependencies
- `strands`: Bedrock AgentCore framework
- `boto3`: AWS SDK
- `alex-database`: Database integration

## Usage

### Direct Function Call
```python
from agent import create_agent_and_run

result = create_agent_and_run(
    job_id="job123",
    portfolio_data=portfolio_data,
    user_id="user123"
)
```

### Bedrock AgentCore Runtime
```python
from agent import agent

app = agent()
# Deploy to AWS Bedrock AgentCore
```

## Testing

### Simple Test (Local)
```bash
cd backend/agent_charter
uv run test_simple.py
```

Tests basic functionality with simple portfolio data and database integration.

### Full Test (Bedrock)
```bash
cd backend/agent_charter  
uv run test_full.py
```

Tests comprehensive portfolio analysis with multiple accounts and complex allocations.

## Chart Types

The agent generates these chart types:

1. **Asset Class Distribution** (pie chart)
   - Equity, Fixed Income, Real Estate, Cash allocation

2. **Geographic Exposure** (bar chart)
   - North America, Europe, Asia Pacific, Emerging Markets

3. **Sector Breakdown** (donut chart)
   - Technology, Healthcare, Financials, etc.

4. **Account Distribution** (pie chart)
   - 401(k), IRA, Roth IRA, Taxable accounts

5. **Top Holdings** (horizontal bar chart)
   - Largest positions by value

6. **Tax Efficiency** (pie/bar chart)
   - Tax-advantaged vs taxable account allocation

## Error Handling

The agent handles various error conditions:

- Missing or null price data (uses default values)
- Invalid JSON output (returns error message)
- Empty portfolio data (generates appropriate error)
- Database connection issues (logged but non-blocking)

## Database Integration

Charts are automatically saved to the database using the `alex-database` package:

```python
success = db.jobs.update_charts(job_id, charts_data)
```

The chart data is stored with the job record for retrieval by the frontend.

## Performance

- **Portfolio Analysis**: O(n) where n is number of positions
- **Chart Generation**: Single agent call with structured output
- **JSON Processing**: Efficient parsing and validation
- **Database Storage**: Batch update of all charts

## Monitoring

Key metrics to monitor:
- Chart generation success rate
- JSON parsing errors
- Database save failures
- Agent execution time
- Model response quality

## Migration Notes

### From OpenAI Agents SDK
- Removed `Runner.run()` pattern
- Replaced `LitellmModel` with `BedrockModel`
- Simplified to direct `agent()` calls
- Removed tool integration (charts use structured output)

### Benefits
- Direct AWS Bedrock integration
- Reduced latency (no LiteLLM proxy)
- Better error handling
- Simplified architecture
- Native AWS deployment

## Future Enhancements

Potential improvements:
- Dynamic chart type selection based on portfolio characteristics
- Interactive chart configuration
- Custom color schemes
- Chart export capabilities
- Real-time chart updates
- Advanced analytics integration