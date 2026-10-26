"""HTTP collector: scrape and save only when the website requests a collection."""

import json
import os

from flask import Flask, jsonify, request
import psycopg2

from platforms import PLATFORMS, resolve_url
from scraper import ScrapeError, save_listings, scrape


def create_app(platform):
    if platform not in PLATFORMS:
        raise ValueError("COLLECTOR_PLATFORM must be cartlane, tao, or lazora")
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(status="ok", platform=platform)

    @app.post("/collect")
    def collect():
        payload = request.get_json(silent=True)
        try:
            selected, url = resolve_url(payload.get("url") if isinstance(payload, dict) else None)
            if selected != platform:
                raise ValueError("This URL belongs to another collector.")
        except ValueError as error:
            return jsonify(error=str(error)), 400

        try:
            listings = scrape(url)
            if not listings:
                return jsonify(error="No products were found at that URL."), 404
            save_listings(listings)
        except ScrapeError:
            app.logger.exception("Collection failed for %s", url)
            return jsonify(error="Could not retrieve this product. Check the URL and try again."), 502
        except psycopg2.Error:
            app.logger.exception("Could not save collected listings")
            return jsonify(error="The database is unavailable. Please try again shortly."), 503

        # Dates and Decimal prices retain the same representation as the scraper CLI.
        return app.response_class(json.dumps({"listings": listings}, default=str), mimetype="application/json")

    return app


if __name__ == "__main__":
    create_app(os.environ["COLLECTOR_PLATFORM"]).run(host="0.0.0.0", port=8000)
