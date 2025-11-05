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


@app.route("/api/sensors/", methods=["GET"])
def current_state():
    return {k: v.model_dump() for k, v in current_state_map.items()}, HTTPStatus.OK
    

if __name__ == "__main__":
    if hmac_secret_key is None:
        print("Missing WEBHOOK_SECRET_KEY")
        sys.exit(1)
    app.run(host="0.0.0.0", port=port, debug=debug)
