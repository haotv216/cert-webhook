"""
Test script for webhook SENDER.
This script helps test the webhook by providing a simple callback receiver.
"""
import json
from flask import Flask, request
from threading import Thread
import time

app = Flask(__name__)
received_webhooks = []


@app.route("/test-callback", methods=["POST"])
def test_callback():
    """Simple callback endpoint to receive webhooks."""
    data = request.get_json()
    received_webhooks.append({
        "timestamp": time.time(),
        "data": data
    })
    print("\n" + "="*50)
    print("WEBHOOK RECEIVED!")
    print("="*50)
    print(json.dumps(data, indent=2))
    print("="*50 + "\n")
    return {"status": "ok", "message": "Webhook received"}, 200


@app.route("/test-callback/list", methods=["GET"])
def list_received():
    """List all received webhooks."""
    return {
        "total": len(received_webhooks),
        "webhooks": received_webhooks
    }, 200


if __name__ == "__main__":
    print("Starting test callback server on http://localhost:9000")
    print("Use this URL as callback_url: http://localhost:9000/test-callback")
    print("View received webhooks at: http://localhost:9000/test-callback/list")
    app.run(host="0.0.0.0", port=9000, debug=True)

