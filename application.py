import json
import logging
import logging
import os
from datetime import datetime
from http import HTTPStatus
from typing import Literal
from unittest import case

import flask
from dotenv import load_dotenv
from flask import Flask, request
from pydantic import BaseModel, TypeAdapter

# Load configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)
debug = os.getenv("DEBUG") in ["true", "True", "1"]
logger = logging.getLogger(__name__)
port = int(os.environ.get("PORT", 8000))

# Set up the application
app = Flask(__name__)


# Our latest readings; this is going to be our "memory"
class CurrentState(BaseModel):
    timestamp: datetime
    temperature: int | None = None
    humidity: int | None = None
    pressure: int | None = None


current_state_map: dict[str, CurrentState] = {}


def update_state(key: str, state: CurrentState):
    last_state = current_state_map.get(key, None)
    if last_state is None or state.timestamp > last_state.timestamp:
        current_state_map[key] = state


def handle_webhook() -> bool:
    event_type = request.args.get("Event")  # type of event
    if not event_type:
        return False

    parsed_datetime = datetime.strptime(request.args.get("DT_Event"), "%Y-%m-%dT%H:%M:%SZ")  # datetime
    key = request.args.get("DeviceSN")  # serial number sans colons
    _ = request.args.get("APSN")  # access point serial number
    p1 = request.args.get("Param1")  # humidity
    p2 = request.args.get("Param2")  # temperature or pressure
    _ = request.args.get("RF")  # field strength in 0.1 dBm
    _ = request.args.get("Flags")  # state of the sensor
    _ = request.args.get("BaseSN")  # AiroX serial number
    _ = request.args.get("AssetSN")  # AssetTag serial number
    _ = request.args.get("Unit")  # unit
    _ = request.args.get("Decimals")  # number of decimals

    _ = request.args.get("DeviceID")  # deprecated
    _ = request.args.get("APID")  # deprecated

    state = CurrentState(
        timestamp=parsed_datetime,
    )

    match int(event_type):
        case 9:  # humidity or temperature
            state.humidity = int(p1) if int(p1) else None
            state.temperature = int(p2) if int(p2) else None
        case 12:  # pressure
            state.pressure = int(p2)
        case _:
            logger.info("Encountered unknown event type: %s. Provided data: Param1=%s, Param2=%s", str(event_type), str(p1), str(p2))
            return True

    update_state(key, state)
    return True


@app.route("/api/sensors/", methods=["GET"])
def handle_get():
    if handle_webhook():
        return "", HTTPStatus.NO_CONTENT

    type_adapter = TypeAdapter(dict[str, CurrentState])

    resp = flask.Response(
        type_adapter.dump_json(current_state_map),
    )
    resp.content_type = "application/json"
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.status = HTTPStatus.OK
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=debug)
