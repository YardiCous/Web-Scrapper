"""HTTP entry point for the same normalisation stage used by the Kafka worker."""
from flask import Flask, jsonify, request

from .pipeline import normalise_record

app = Flask(__name__)


@app.post('/normalise')
def normalise():
    payload = request.get_json(silent=True)
    listings = payload.get('listings') if isinstance(payload, dict) else None
    if not isinstance(listings, list) or not listings or any(not isinstance(row, dict) for row in listings):
        return jsonify(error='Provide a non-empty listings array.'), 400
    try:
        return jsonify(listings=[normalise_record(row) for row in listings])
    except (ValueError, KeyError, TypeError):
        return jsonify(error='Invalid raw listing.'), 400


@app.get('/healthz')
def healthz():
    return jsonify(status='ok')
