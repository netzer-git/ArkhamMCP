import requests
import sys

try:
    # Simple test of the root endpoint
    response = requests.get("http://localhost:8000/")
    
    if response.status_code == 200:
        print("SUCCESS: Server is running!")
        print(f"Response: {response.text}")
        sys.exit(0)
    else:
        print(f"ERROR: Server returned status code {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to connect to server: {str(e)}")
    sys.exit(1)
