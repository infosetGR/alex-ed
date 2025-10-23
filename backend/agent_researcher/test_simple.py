"""
Test the Researcher Agent with browser tools (simple test).
"""

import os
from agent import create_agent_and_run

def test_researcher_agent():
    """Test the researcher agent with a specific topic."""
    print("🔍 Testing Researcher Agent with Browser...")
    
    # Test with a specific topic
    topic = "Tesla Stock Analysis"
    print(f"📊 Research Topic: {topic}")
    
    try:
        # Set up environment variables for testing
        os.environ.setdefault("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        os.environ.setdefault("BEDROCK_REGION", "us-west-2")
        
        # Note: ALEX_API_ENDPOINT and ALEX_API_KEY should be set for document ingestion
        # If not set, the agent will note this in local mode
        
        print(f"🌐 Using model: {os.environ.get('BEDROCK_MODEL_ID')}")
        print(f"🌍 Using region: {os.environ.get('BEDROCK_REGION')}")
        
        print("\n🔍 Running Researcher Agent with Browser...")
        print("   The agent will use real browser automation to visit financial websites")
        result = create_agent_and_run(topic)
        
        print("📊 Researcher Agent Result:")
        print("=" * 50)
        print(result)
        print("=" * 50)
        
        # Basic validation
        if result and len(result) > 50:
            print("✅ Researcher Agent generated substantial output")
        else:
            print("⚠️ Researcher Agent output seems short or empty")
        
        if "Tesla" in result or "TSLA" in result:
            print("✅ Response appears to be about the requested topic")
        else:
            print("⚠️ Response may not be about the requested topic")
        
        # Check for browser activity indicators
        result_lower = result.lower()
        browser_indicators = ["website", "browser", "visited", "navigated", "page", "url"]
        if any(indicator in result_lower for indicator in browser_indicators):
            print("✅ Response indicates browser activity")
        else:
            print("⚠️ No clear evidence of browser usage in response")
        
        print("✅ Researcher Agent test completed")
        
    except Exception as e:
        print(f"❌ Error during Researcher Agent test: {e}")
        import traceback
        traceback.print_exc()

def test_researcher_agent_auto():
    """Test the researcher agent with automatic topic selection."""
    print("\n🔍 Testing Researcher Agent (Auto Topic Selection)...")
    
    try:
        print("\n🔍 Running Researcher Agent with automatic topic selection...")
        print("   The agent will use browser to find trending financial topics")
        result = create_agent_and_run()  # No topic provided
        
        print("📊 Researcher Agent Auto Result:")
        print("=" * 50)
        print(result)
        print("=" * 50)
        
        # Basic validation
        if result and len(result) > 50:
            print("✅ Researcher Agent generated substantial output")
        else:
            print("⚠️ Researcher Agent output seems short or empty")
        
        # Check for browser activity indicators
        result_lower = result.lower()
        browser_indicators = ["website", "browser", "visited", "navigated", "page", "trending"]
        if any(indicator in result_lower for indicator in browser_indicators):
            print("✅ Response indicates browser activity and topic discovery")
        else:
            print("⚠️ No clear evidence of browser usage in response")
        
        print("✅ Researcher Agent auto test completed")
        
    except Exception as e:
        print(f"❌ Error during Researcher Agent auto test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_researcher_agent()
    test_researcher_agent_auto()