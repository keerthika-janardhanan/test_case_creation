"""Test the keyword-inspect API endpoint."""
import requests
import json

def test_keyword_inspect_api():
    """Test keyword-inspect endpoint via FastAPI."""
    base_url = "http://localhost:8001"
    
    # Prepare request payload
    payload = {
        "keyword": "Create Supplier",
        "repoPath": "",  # Empty to use default framework
        "maxAssets": 5
    }
    
    print("Testing /api/agentic/keyword-inspect endpoint...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{base_url}/api/agentic/keyword-inspect",
            json=payload,
            timeout=30
        )
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse:")
            print(f"- Keyword: {data['keyword']}")
            print(f"- Status: {data['status']}")
            print(f"- Existing Assets: {len(data['existingAssets'])}")
            print(f"- Refined Flow: {'Yes' if data['refinedRecorderFlow'] else 'No'}")
            print(f"- Vector Context: flowAvailable={data['vectorContext']['flowAvailable']}, steps={data['vectorContext']['vectorStepsCount']}")
            print(f"- Messages: {len(data['messages'])}")
            for msg in data['messages']:
                print(f"  - {msg}")
            
            if data['existingAssets']:
                print(f"\nExisting Assets:")
                for asset in data['existingAssets']:
                    print(f"  - {asset['path']} (relevance: {asset.get('relevance')}, isTest: {asset['isTest']})")
                    print(f"    Snippet: {asset['snippet'][:100]}...")
            
            print("\n✓ API endpoint test passed!")
        else:
            print(f"\n✗ Request failed: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("\n⚠ FastAPI server is not running on port 8001")
        print("Please start the server with: uvicorn app.api.main:app --reload --port 8001")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_keyword_inspect_api()
