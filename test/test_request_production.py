"""
Production example - Gửi request đến webhook với callback_url thực tế
"""
import requests
import json

# Webhook SENDER URL (deploy của bạn)
WEBHOOK_URL = "https://your-webhook-server.com/api/v1.0/cert/add"

# Callback URL - URL của hệ thống cần cert để nhận kết quả
# Đây là endpoint mà hệ thống của bạn cung cấp để nhận webhook callback
CALLBACK_URL = "https://your-system.com/api/webhooks/cert-callback"

# Request payload
payload = {
    "callback_url": CALLBACK_URL,  # Webhook sẽ POST kết quả về đây
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
        print(f"\nWebhook sẽ gọi {CALLBACK_URL} khi cert được tạo xong")
        print("=" * 50)
    else:
        print("\n❌ Request failed!")
        
except requests.exceptions.ConnectionError:
    print("\n❌ Error: Cannot connect to webhook server!")
    print("Make sure webhook server is running and accessible")
except Exception as e:
    print(f"\n❌ Error: {str(e)}")

