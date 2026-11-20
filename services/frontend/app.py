"""Browser pages and API forwarding; all collection and processing lives behind the gateway."""
import os

import requests
from flask import Flask, jsonify, render_template, request, url_for

from shared.platforms import resolve_product_url

app = Flask(__name__)


def _gateway(method, path, **kwargs):
    base = os.environ.get('GATEWAY_URL', 'http://localhost:8500').rstrip('/')
    return requests.request(method, base + path, timeout=(3.05, 180), **kwargs)


def _get(request_id):
    response = _gateway('GET', '/api/searches/' + request_id)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/search')
def lookup():
    pasted_url = request.args.get('url', '')
    try:
        _, url = resolve_product_url(pasted_url)
    except ValueError as error:
        return render_template('index.html', pasted_url=pasted_url, error=str(error)), 400
    try:
        response = _gateway('POST', '/api/searches', json={'url': url})
        response.raise_for_status()
        job = response.json()
    except (requests.RequestException, ValueError, KeyError):
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
    except (requests.RequestException, ValueError):
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
    try:
        response = _gateway('POST', '/api/searches', json=request.get_json(silent=True))
        body = response.json()
        result = jsonify(body)
        result.status_code = response.status_code
        if 'request_id' in body:
            result.headers['Location'] = url_for('get_search', request_id=body['request_id'])
        return result
    except (requests.RequestException, ValueError):
        app.logger.exception('Gateway unavailable')
        return jsonify(error='The comparison service is unavailable.'), 503


@app.get('/api/searches/<uuid:request_id>')
def get_search(request_id):
    try:
        response = _gateway('GET', '/api/searches/' + str(request_id))
        return jsonify(response.json()), response.status_code
    except (requests.RequestException, ValueError):
        app.logger.exception('Gateway unavailable')
        return jsonify(error='The comparison service is unavailable.'), 503


@app.get('/healthz')
def healthz():
    return jsonify(status='ok')


@app.get('/health')
def health():
    try:
        response = _gateway('GET', '/health')
        response.raise_for_status()
        return jsonify(response.json())
    except (requests.RequestException, ValueError):
        return jsonify(status='error', error='The gateway is unavailable.'), 503


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))
