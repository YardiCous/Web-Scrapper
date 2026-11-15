import os
from flask import Flask, render_template, request, jsonify, url_for
import requests

try:
    from . import db, searches
    from .platforms import resolve_url
except ImportError:
    import db
    import searches
    from platforms import resolve_url

app = Flask(__name__)


def _gateway(method, path, **kwargs):
    response = requests.request(method, os.environ['GATEWAY_URL'].rstrip('/') + path,
                                timeout=(3.05, 180), **kwargs)
    response.raise_for_status()
    return response.json()


def _start(url):
    if os.environ.get('GATEWAY_URL'):
        return _gateway('POST', '/api/searches', json={'url': url})
    return searches.start(url)


def _get(request_id):
    if os.environ.get('GATEWAY_URL'):
        try:
            return _gateway('GET', '/api/searches/' + request_id)
        except requests.HTTPError as error:
            if error.response.status_code == 404:
                return None
            raise
    return searches.get(request_id)


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/search')
def lookup():
    pasted_url = request.args.get('url', '')
    try:
        _, url = resolve_url(pasted_url)
    except ValueError as error:
        return render_template('index.html', pasted_url=pasted_url, error=str(error)), 400
    try:
        job = _start(url)
    except Exception:
        app.logger.exception('Product comparison failed')
        return render_template('index.html', pasted_url=pasted_url,
                               error='Could not complete product comparison. Please try again shortly.'), 502
    if job['status'] == 'complete':
        return render_template('search.html', pasted_url=url, listings=job['listings'])
    return render_template('pending.html', pasted_url=url, job=job), 202


@app.get('/searches/<uuid:request_id>')
def search_result(request_id):
    try:
        job = _get(str(request_id))
    except Exception:
        app.logger.exception('Could not read search result')
        return jsonify(error='The comparison service is unavailable.'), 503
    if job is None:
        return jsonify(error='Search not found.'), 404
    if job['status'] == 'complete':
        return render_template('search.html', pasted_url=job['url'], listings=job['listings'])
    if job['status'] == 'failed':
        return render_template('index.html', pasted_url=job['url'], error=job['error']), 502
    return render_template('pending.html', pasted_url=job['url'], job=job), 202


@app.post('/api/searches')
def create_search():
    payload = request.get_json(silent=True)
    try:
        _, url = resolve_url(payload.get('url') if isinstance(payload, dict) else None)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        job = _start(url)
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
        job = _get(str(request_id))
    except requests.HTTPError as error:
        if error.response.status_code == 404:
            return jsonify(error='Search not found.'), 404
        app.logger.exception('Gateway unavailable')
        return jsonify(error='The comparison service is unavailable.'), 503
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
        if os.environ.get('GATEWAY_URL'):
            return jsonify(_gateway('GET', '/health'))
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
        return jsonify(status='ok', db='up')
    except Exception:
        return jsonify(status='error', error='The database or gateway is unavailable.'), 503


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))
