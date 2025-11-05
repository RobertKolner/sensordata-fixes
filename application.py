import base64
import hashlib
import hmac
import logging
import os
import sys
from datetime import datetime
from http import HTTPStatus

from dotenv import load_dotenv
from flask import Flask, request, abort
from flask import jsonify
from pydantic import BaseModel, ValidationError

from webhook_model import WebhookRequestBody

DEVICE_SN_LABELS = {
    "00E6D504": "Lab 1",
    "00D6FE76": "Lab 2",
    "00B66B1D": "Lab 3",
    "00E96AA7": "Lab 4",
    "00E4C3FD": "Lab 5",
    "0087BA71": "Lab 6",
    "004326FE": "Pressure",
    "100D99F666": "Temp & Humidity"
}

# Load configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)
debug = os.getenv("DEBUG") in ["true", "True", "1"]
logger = logging.getLogger(__name__)
port = int(os.environ.get("PORT", 8000))
hmac_secret_key = os.getenv("WEBHOOK_SECRET_KEY")

# Set up the application
app = Flask(__name__)


# Our latest readings; this is going to be our "memory"
class CurrentState(BaseModel):
    timestamp: datetime
    value: str | float


current_state_map: dict[str, CurrentState] = {}


def parse_authorization_header() -> tuple[str, str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise ValueError("Missing authorization header")

    try:
        scheme, value = auth_header.split(" ")
    except ValueError:
        raise ValueError("Invalid authorization header")

    if scheme != "HMAC-SHA256":
        raise ValueError("Invalid authorization scheme")

    try:
        signature, nonce = value.split(":")
    except ValueError:
        raise ValueError("Invalid authorization value format")

    return signature, nonce


def verify_signature(payload, signature, nonce):
    key = (hmac_secret_key + nonce).encode("utf-8")
    computed_hmac = hmac.new(key, payload, hashlib.sha256).digest()
    computed_signature = base64.b64encode(computed_hmac).decode()
    if not hmac.compare_digest(computed_signature, signature):
        raise ValueError(f"Invalid signature: {computed_signature} != {signature}")


def handle_webhook(webhook_request: WebhookRequestBody):
    for item in webhook_request.root:
        message_id = item.headers.message_id
        logging.info("processing new message_id=%s", message_id)

        for sensor in item.payload:
            device_sn = sensor.device_sn
            last_state = current_state_map.get(device_sn, None)
            if last_state is None or sensor.event_date > last_state.timestamp:
                current_state_map[device_sn] = CurrentState(
                    timestamp=sensor.event_date, value=sensor.measurement.value
                )


@app.route("/api/sensors/", methods=["POST"])
def webhook():
    logger.info("webhook triggered")

    try:
        signature, nonce = parse_authorization_header()
        verify_signature(request.data, signature, nonce)
    except ValueError as e:
        logging.error("authorization error: %s", str(e))
        abort(HTTPStatus.UNAUTHORIZED)

    try:
        request_body = WebhookRequestBody.model_validate_json(request.data)
    except ValidationError as e:
        abort(HTTPStatus.UNPROCESSABLE_ENTITY, str(e))

    logger.info("received body with %d items", len(request_body.root))
    handle_webhook(request_body)
    return "", HTTPStatus.NO_CONTENT


@app.route("/api/sensors/", methods=["GET"])
def current_state():
    # Optional: sort by timestamp descending
    sorted_data = dict(sorted(current_state_map.items(), key=lambda item: item[1].timestamp, reverse=True))
    mapped_data = {
        DEVICE_SN_LABELS.get(k, k): v.model_dump()
        for k, v in current_state_map.items()
    }
    return jsonify(mapped_data), HTTPStatus.OK

if __name__ == "__main__":
    if hmac_secret_key is None:
        print("Missing WEBHOOK_SECRET_KEY")
        sys.exit(1)
    app.run(host="0.0.0.0", port=port, debug=debug)
