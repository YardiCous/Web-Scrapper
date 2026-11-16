# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f services/maintenance/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CDC_DATA_DIR=/app/data
WORKDIR /app

COPY services/maintenance/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/__init__.py
COPY services/maintenance/ ./services/maintenance/
COPY shared/ ./shared/
COPY data/samples/ ./data/samples/

RUN useradd --uid 10001 --no-create-home app
USER 10001

ENTRYPOINT ["python", "-m", "services.maintenance"]
