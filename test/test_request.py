"""
Quick test script to send request to webhook
"""
import requests
import json

# Your webhook URL (webhook sender endpoint)
WEBHOOK_URL = "http://localhost:8000/api/v1.0/cert/add"

# Callback URL - URL của hệ thống cần cert để nhận kết quả
# TEST: Dùng webhook.site để test
CALLBACK_URL = "https://webhook.site/b41fb82a-63c6-49c1-9d49-c2a55e1e54d0"

# PRODUCTION: Thay bằng URL thực của hệ thống cần cert
# Ví dụ:
# CALLBACK_URL = "https://your-system.com/api/webhooks/cert-callback"
# CALLBACK_URL = "https://api.yourdomain.com/v1/cert/notify"

# Request payload
payload = {
    "callback_url": CALLBACK_URL,
    "cname_id": 123,
    "domain": "example.com",
    "email": "admin@example.com",
    "user_id": 42
}

print("Sending request to webhook...")
print(f"Webhook URL: {WEBHOOK_URL}")
print(f"Callback URL: {CALLBACK_URL}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("-" * 50)

try:
    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 202:
        request_id = response.json().get("request_id")
        print("\n" + "=" * 50)
        print("✅ Request accepted!")
        print(f"Request ID: {request_id}")
        print(f"\nCheck status at: http://localhost:8000/status/{request_id}")
        print(f"Check webhook.site to see the callback: {CALLBACK_URL}")
        print("=" * 50)
    else:
        print("\n❌ Request failed!")
        
except requests.exceptions.ConnectionError:
    print("\n❌ Error: Cannot connect to webhook server!")
    print("Make sure webhook server is running: python app.py")
except Exception as e:
    print(f"\n❌ Error: {str(e)}")

