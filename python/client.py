
import requests
import sys

API_URL = "http://localhost:8000/process"

def upload_file(file_path):
    print(f"Uploading {file_path} to {API_URL}...")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(API_URL, files=files)
            
        if response.status_code == 200:
            print("\n✅ Success! Response:")
            print(response.json())
        else:
            print(f"\n❌ Error {response.status_code}:")
            print(response.text)
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python client_example.py <path_to_file>")
    else:
        upload_file(sys.argv[1])
