import json
import logging
import os
import time

import requests
import stripe
from flask import Flask, request, jsonify
from svix.webhooks import Webhook, WebhookVerificationError

LOKI_URL = os.environ["LOKI_URL"].rstrip("/") + "/loki/api/v1/push"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingester")

app = Flask(__name__)


def push_to_loki(labels: dict, event: dict) -> None:
    ts_ns = str(time.time_ns())
    payload = {
        "streams": [
            {
                "stream": labels,
                "values": [[ts_ns, json.dumps(event, separators=(",", ":"))]],
            }
        ]
    }
    r = requests.post(LOKI_URL, json=payload, timeout=5)
    if r.status_code >= 300:
        log.error("loki push failed: %s %s", r.status_code, r.text[:200])
        r.raise_for_status()


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.post("/webhooks/stripe")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return "stripe disabled", 503
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.warning("stripe sig verify failed: %s", e)
        return "bad signature", 400

    event_type = event.get("type", "unknown")
    push_to_loki(
        {"job": "webhooks", "provider": "stripe", "event_type": event_type},
        event,
    )
    log.info("stripe %s id=%s", event_type, event.get("id"))
    return jsonify(received=True), 200


@app.post("/webhooks/resend")
def resend_webhook():
    if not RESEND_WEBHOOK_SECRET:
        return "resend disabled", 503
    payload = request.get_data()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    try:
        wh = Webhook(RESEND_WEBHOOK_SECRET)
        event = wh.verify(payload, headers)
    except WebhookVerificationError as e:
        log.warning("resend sig verify failed: %s", e)
        return "bad signature", 400

    event_type = event.get("type", "unknown")
    push_to_loki(
        {"job": "webhooks", "provider": "resend", "event_type": event_type},
        event,
    )
    log.info("resend %s", event_type)
    return jsonify(received=True), 200
