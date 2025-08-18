#!/usr/bin/env python3
"""
Simple test script to verify the Flask application works correctly.
"""

import requests
import json
import time
import sys

def test_health_endpoint(base_url):
    """Test the health endpoint."""
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") == True:
                print("✅ Health endpoint working")
                return True
            else:
                print("❌ Health endpoint returned unexpected data")
                return False
        else:
            print(f"❌ Health endpoint failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")
        return False

def test_session_endpoint(base_url):
    """Test the session creation endpoint."""
    try:
        response = requests.post(f"{base_url}/api/session", 
                               headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            data = response.json()
            if "sessionId" in data:
                print("✅ Session endpoint working")
                return data["sessionId"]
            else:
                print("❌ Session endpoint missing sessionId")
                return None
        else:
            print(f"❌ Session endpoint failed with status {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Session endpoint error: {e}")
        return None

def test_openai_chat_endpoint(base_url, session_id):
    """Test the OpenAI chat endpoint."""
    try:
        payload = {
            "text": "Hello, this is a test message",
            "sessionId": session_id
        }
        response = requests.post(f"{base_url}/api/openai/chat", 
                               headers={"Content-Type": "application/json"},
                               json=payload)
        if response.status_code == 200:
            data = response.json()
            if "reply" in data:
                print("✅ OpenAI chat endpoint working")
                return True
            else:
                print("❌ OpenAI chat endpoint missing reply")
                return False
        else:
            print(f"❌ OpenAI chat endpoint failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ OpenAI chat endpoint error: {e}")
        return False

def test_muse_start_endpoint(base_url, session_id):
    """Test the Musetalk start endpoint."""
    try:
        payload = {
            "sessionId": session_id,
            "avatarId": "default-01",
            "text": "Test avatar generation"
        }
        response = requests.post(f"{base_url}/api/muse/start", 
                               headers={"Content-Type": "application/json"},
                               json=payload)
        if response.status_code == 200:
            data = response.json()
            if "mode" in data and data["mode"] in ["mse", "file"]:
                print("✅ Musetalk start endpoint working")
                return True
            else:
                print("❌ Musetalk start endpoint missing or invalid mode")
                return False
        else:
            print(f"❌ Musetalk start endpoint failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Musetalk start endpoint error: {e}")
        return False

def main():
    """Run all tests."""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Avatar Chat Flask Application")
    print("=" * 50)
    
    # Test health endpoint
    if not test_health_endpoint(base_url):
        print("\n❌ Application may not be running. Please start it with: python app.py")
        sys.exit(1)
    
    # Test session endpoint
    session_id = test_session_endpoint(base_url)
    if not session_id:
        print("\n❌ Session creation failed")
        sys.exit(1)
    
    # Test OpenAI chat endpoint
    if not test_openai_chat_endpoint(base_url, session_id):
        print("\n❌ OpenAI chat failed")
        sys.exit(1)
    
    # Test Musetalk start endpoint
    if not test_muse_start_endpoint(base_url, session_id):
        print("\n❌ Musetalk start failed")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("🎉 All tests passed! Application is working correctly.")
    print(f"🌐 Open your browser and go to: {base_url}")
    print("🎤 Try clicking the microphone button to test the UI!")

if __name__ == "__main__":
    main()
