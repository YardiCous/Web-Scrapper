# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f services/scorer/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080
WORKDIR /app

COPY services/scorer/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/__init__.py
COPY services/scorer/ ./services/scorer/

RUN useradd --uid 10001 --no-create-home app
USER 10001

CMD ["uvicorn", "services.scorer.app:app", "--host", "0.0.0.0", "--port", "8080"]
