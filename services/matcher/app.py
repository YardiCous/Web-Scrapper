"""HTTP entry point for matching cleaned listings into product clusters."""
from flask import Flask, jsonify, request

from .pipeline import match_listings

app = Flask(__name__)


@app.post('/match')
def match():
    payload = request.get_json(silent=True)
    listings = payload.get('listings') if isinstance(payload, dict) else None
    if not isinstance(listings, list) or not listings or any(not isinstance(row, dict) for row in listings):
        return jsonify(error='Provide a non-empty listings array.'), 400
    try:
        ids = [row['listing_id'] for row in listings]
        if len(ids) != len(set(ids)):
            return jsonify(error='Listing identifiers must be unique.'), 400
        return jsonify(listings=match_listings(listings))
    except (ValueError, KeyError, TypeError):
        return jsonify(error='Invalid cleaned listing.'), 400


@app.get('/healthz')
def healthz():
    return jsonify(status='ok')
