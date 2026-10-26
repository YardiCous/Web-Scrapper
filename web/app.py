import os

from flask import Flask, render_template, request, jsonify
import requests

import db
from platforms import PLATFORMS, resolve_url

app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/search")
def lookup():
    pasted_url = request.args.get("url", "")
    try:
        platform, url = resolve_url(pasted_url)
    except ValueError as error:
        return render_template("index.html", pasted_url=pasted_url, error=str(error)), 400

    endpoint = os.environ.get(
        f"COLLECTOR_{platform.upper()}_URL", f"http://localhost:{PLATFORMS[platform]['port']}"
    ).rstrip("/")
    try:
        response = requests.post(endpoint + "/collect", json={"url": url}, timeout=(3.05, 120))
        response.raise_for_status()
        listings = response.json()["listings"]
        if not isinstance(listings, list) or not listings or any(not isinstance(item, dict) for item in listings):
            raise ValueError("Invalid collector response")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        app.logger.exception("Product collection failed using %s", platform)
        return render_template(
            "index.html", pasted_url=pasted_url,
            error="Could not retrieve this product. Check the URL or try again shortly.",
        ), 502

    return render_template("search.html", pasted_url=pasted_url, listings=listings)

@app.get("/health")
def health():
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify(status="ok", db="up")
    except Exception as e:
        return jsonify(status="error", db=str(e)), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
