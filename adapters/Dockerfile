# Build context is the repository root (infra/scripts/images.sh): the image carries the teammates' code
# as is, plus the adapters and infra's Kafka helpers.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/web \
    CDC_DATA_DIR=/app
WORKDIR /app

COPY adapters/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY infra/images/tools/cdc_tools/__init__.py infra/images/tools/cdc_tools/common.py ./cdc_tools/
COPY web/scraper.py ./web/
COPY normaliser/core ./normaliser/core
COPY adapters ./adapters

RUN useradd --uid 10001 --no-create-home app
USER 10001

ENTRYPOINT ["python", "-m", "adapters"]
