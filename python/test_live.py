import requests
import sys
import os

# Your live Render URL
API_URL = "https://apirfq.onrender.com/process"

def upload_file(file_path):
    print(f"🚀 Uploading {file_path} to {API_URL}...")
    
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found: {file_path}")
        return

    try:
        with open(file_path, 'rb') as f:
            # Determine content type based on extension
            files = {'file': f}
            
            # Send POST request
            response = requests.post(API_URL, files=files, timeout=300) # 5 min timeout for AI processing
            
        if response.status_code == 200:
            print("\n✅ Valid Response Received!")
            print("------------------------------------------------")
            print(response.json())
            print("------------------------------------------------")
        else:
            print(f"\n❌ Error {response.status_code}:")
            print(response.text)
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_live.py <path_to_pdf_or_image>")
        print("Example: python test_live.py sample.pdf")
    else:
        upload_file(sys.argv[1])
