# Build context is infra/ (see scripts/images.sh) so the schemas and samples can be baked in.
# Two targets: `tools` (cdc-tools: jobs and smoke-consumer) and `placeholder` (cdc-placeholder: the echo
# server that stands in for teammates' HTTP services, with no args needed in their manifests).
FROM python:3.14.9-slim AS tools

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CDC_DATA_DIR=/app
WORKDIR /app

COPY images/tools/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schemas ./schemas
COPY samples ./samples
COPY images/tools/cdc_tools ./cdc_tools

RUN useradd --uid 10001 --no-create-home app
USER 10001

ENTRYPOINT ["python", "-m", "cdc_tools"]

FROM tools AS placeholder
CMD ["echo"]
