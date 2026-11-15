"""Search API and orchestration, independent of the browser frontend."""
from flask import Flask, jsonify, request, url_for

from shared import database
from shared.platforms import resolve_url
from . import searches

app = Flask(__name__)


@app.post('/api/searches')
def create_search():
    payload = request.get_json(silent=True)
    try:
        _, url = resolve_url(payload.get('url') if isinstance(payload, dict) else None)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        job = searches.start(url)
    except Exception:
        app.logger.exception('Could not start search')
        return jsonify(error='The comparison service is unavailable. Please try again shortly.'), 503
    response = jsonify(job)
    response.status_code = 202 if job['status'] == 'pending' else 200
    response.headers['Location'] = url_for('get_search', request_id=job['request_id'])
    return response


@app.get('/api/searches/<uuid:request_id>')
def get_search(request_id):
    try:
        job = searches.get(str(request_id))
    except Exception:
        app.logger.exception('Could not read search progress')
        return jsonify(error='The comparison service is unavailable.'), 503
    return (jsonify(job), 200) if job else (jsonify(error='Search not found.'), 404)


@app.get('/healthz')
def healthz():
    return jsonify(status='ok')


@app.get('/health')
def health():
    try:
        with database.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
        return jsonify(status='ok', db='up')
    except Exception:
        return jsonify(status='error', error='The database is unavailable.'), 503
