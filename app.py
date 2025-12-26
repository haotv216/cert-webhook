import os
import uuid
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CERT_API_BASE_URL = os.getenv("CERT_API_BASE_URL", "http://103.143.207.21:5000")
CERT_API_AUTH_KEY = os.getenv("CERT_API_AUTH_KEY", "")
WEBHOOK_TIMEOUT = int(os.getenv("WEBHOOK_TIMEOUT", "30"))
WEBHOOK_RETRY_COUNT = int(os.getenv("WEBHOOK_RETRY_COUNT", "3"))
WEBHOOK_RETRY_DELAY = int(os.getenv("WEBHOOK_RETRY_DELAY", "5"))

# Storage for tracking requests
request_tracking: Dict[str, Dict[str, Any]] = {}


def _error(message: str, status: int = 400):
    """Return a JSON error response."""
    return jsonify({"status": "error", "message": message}), status


def _send_webhook(callback_url: str, payload: Dict[str, Any], retry_count: int = 0) -> bool:
    """
    Send webhook to callback_url with retry logic.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"Sending webhook to {callback_url}, attempt {retry_count + 1}")
        response = requests.post(
            callback_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=WEBHOOK_TIMEOUT,
        )
        response.raise_for_status()
        logger.info(f"Webhook sent successfully to {callback_url}, status: {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        logger.warning(f"Webhook timeout to {callback_url}, attempt {retry_count + 1}")
        if retry_count < WEBHOOK_RETRY_COUNT - 1:
            import time
            time.sleep(WEBHOOK_RETRY_DELAY)
            return _send_webhook(callback_url, payload, retry_count + 1)
        logger.error(f"Failed to send webhook to {callback_url} after {WEBHOOK_RETRY_COUNT} attempts")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Webhook error to {callback_url}: {str(e)}, attempt {retry_count + 1}")
        if retry_count < WEBHOOK_RETRY_COUNT - 1:
            import time
            time.sleep(WEBHOOK_RETRY_DELAY)
            return _send_webhook(callback_url, payload, retry_count + 1)
        logger.error(f"Failed to send webhook to {callback_url} after {WEBHOOK_RETRY_COUNT} attempts")
        return False


def _call_cert_api(request_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Call the external cert API and return the response.
    Returns: (result, error_info) where error_info is None if successful.
    """
    api_url = f"{CERT_API_BASE_URL}/api/v1.0/cert/add"
    
    try:
        logger.info(f"Calling cert API: {api_url}")
        headers = {
            "Content-Type": "application/json",
        }
        if CERT_API_AUTH_KEY:
            headers["X-AUTH-KEY"] = CERT_API_AUTH_KEY
        
        response = requests.post(
            api_url,
            json=request_data,
            headers=headers,
            timeout=60,  # Longer timeout for cert generation
        )
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Cert API response received, status: {response.status_code}")
        return result, None
        
    except requests.exceptions.Timeout:
        error_info = {
            "error_type": "timeout",
            "message": "Cert API request timed out",
            "api_url": api_url,
        }
        logger.error(f"Cert API timeout: {api_url}")
        return None, error_info
    except requests.exceptions.HTTPError as e:
        error_info = {
            "error_type": "http_error",
            "status_code": e.response.status_code if e.response else None,
            "message": str(e),
            "api_url": api_url,
        }
        try:
            if e.response:
                error_info["response_body"] = e.response.json()
        except:
            pass
        logger.error(f"Cert API HTTP error: {e.response.status_code if e.response else 'unknown'} - {str(e)}")
        return None, error_info
    except requests.exceptions.RequestException as e:
        error_info = {
            "error_type": "request_error",
            "message": str(e),
            "api_url": api_url,
        }
        logger.error(f"Cert API error: {str(e)}")
        return None, error_info


def _process_cert_request(request_id: str, request_data: Dict[str, Any], callback_url: str):
    """
    Background task: Call cert API and send result to callback_url.
    """
    logger.info(f"Processing cert request {request_id} for domain {request_data.get('domain')}")
    
    # Update tracking
    request_tracking[request_id] = {
        "status": "processing",
        "requested_at": datetime.now(timezone.utc).isoformat() + "Z",
        "domain": request_data.get("domain"),
        "callback_url": callback_url,
    }
    
    # Call external cert API
    api_result, error_info = _call_cert_api(request_data)
    
    if api_result is None:
        # API call failed
        error_payload = {
            "status": "error",
            "request_id": request_id,
            "message": "Failed to call cert API",
            "domain": request_data.get("domain"),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }
        if error_info:
            error_payload["error_details"] = error_info
        
        request_tracking[request_id]["status"] = "failed"
        request_tracking[request_id]["error"] = error_info or "API call failed"
        _send_webhook(callback_url, error_payload)
        return
    
    # API call succeeded, send result to callback_url
    webhook_payload = {
        "status": "success",
        "request_id": request_id,
        "domain": request_data.get("domain"),
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "cert_data": api_result,
    }
    
    request_tracking[request_id]["status"] = "completed"
    request_tracking[request_id]["completed_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    request_tracking[request_id]["result"] = api_result
    
    # Send webhook to callback_url
    webhook_sent = _send_webhook(callback_url, webhook_payload)
    if not webhook_sent:
        request_tracking[request_id]["webhook_status"] = "failed"
    else:
        request_tracking[request_id]["webhook_status"] = "sent"


@app.route("/api/v1.0/cert/add", methods=["POST"])
def cert_add():
    """
    Webhook SENDER endpoint.
    Receives request from system, calls external cert API, and sends result to callback_url.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return _error("Missing JSON body")
    
    # Validate required fields
    required_fields = ["callback_url", "cname_id", "domain", "email", "user_id"]
    for field in required_fields:
        if field not in payload:
            return _error(f"Missing required field: {field}")
    
    callback_url = payload.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        return _error("Invalid callback_url")
    
    # Generate request ID
    request_id = str(uuid.uuid4())
    
    # Prepare request data for external API (remove callback_url as it's for our webhook)
    request_data = {
        "cname_id": payload.get("cname_id"),
        "domain": payload.get("domain"),
        "email": payload.get("email"),
        "user_id": payload.get("user_id"),
    }
    
    # Start background processing
    thread = threading.Thread(
        target=_process_cert_request,
        args=(request_id, request_data, callback_url),
        daemon=True
    )
    thread.start()
    
    logger.info(f"Cert request {request_id} queued for processing, callback_url: {callback_url}")
    
    # Return immediate response
    return jsonify({
        "status": "accepted",
        "request_id": request_id,
        "message": "Request received and processing started",
        "domain": payload.get("domain"),
    }), 202


@app.route("/api/v1.0/cert/reject", methods=["POST"])
def cert_reject():
    """
    Webhook SENDER endpoint for rejecting cert.
    Calls external reject API and sends result to callback_url.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return _error("Missing JSON body")
    
    # Validate required fields
    required_fields = ["callback_url", "cname_id", "domain", "email", "user_id"]
    for field in required_fields:
        if field not in payload:
            return _error(f"Missing required field: {field}")
    
    callback_url = payload.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        return _error("Invalid callback_url")
    
    request_id = str(uuid.uuid4())
    
    # Prepare request data for external API
    request_data = {
        "cname_id": payload.get("cname_id"),
        "domain": payload.get("domain"),
        "email": payload.get("email"),
        "user_id": payload.get("user_id"),
    }
    
    # Call external reject API
    api_url = f"{CERT_API_BASE_URL}/api/v1.0/cert/reject"
    
    try:
        headers = {
            "Content-Type": "application/json",
        }
        if CERT_API_AUTH_KEY:
            headers["X-AUTH-KEY"] = CERT_API_AUTH_KEY
        
        response = requests.post(
            api_url,
            json=request_data,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        api_result = response.json()
        
        # Send result to callback_url
        webhook_payload = {
            "status": "success",
            "request_id": request_id,
            "action": "reject",
            "domain": payload.get("domain"),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "result": api_result,
        }
        
        _send_webhook(callback_url, webhook_payload)
        
        return jsonify({
            "status": "success",
            "request_id": request_id,
            "message": "Reject request processed and webhook sent",
        }), 200
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Reject API error: {str(e)}")
        
        # Send error to callback_url
        error_payload = {
            "status": "error",
            "request_id": request_id,
            "action": "reject",
            "message": f"Failed to process reject request: {str(e)}",
            "domain": payload.get("domain"),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }
        _send_webhook(callback_url, error_payload)
        
        return _error(f"Failed to process reject request: {str(e)}", 500)


@app.route("/status/<request_id>", methods=["GET"])
def get_status(request_id):
    """Get status of a cert request."""
    if request_id not in request_tracking:
        return _error("Request not found", 404)
    return jsonify(request_tracking[request_id]), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
