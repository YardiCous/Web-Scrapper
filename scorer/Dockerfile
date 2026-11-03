FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scorer_engine/ scorer_engine/

RUN useradd --uid 10001 --no-create-home scorer
USER 10001

EXPOSE 8080
# Knative injects PORT; default 8080 for docker run.
CMD ["sh", "-c", "exec uvicorn scorer_engine.app:app --host 0.0.0.0 --port ${PORT}"]
