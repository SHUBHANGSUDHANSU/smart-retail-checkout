FROM python:3.11-slim AS api-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SMART_RETAIL_API_HOST=0.0.0.0 \
    SMART_RETAIL_API_PORT=8000 \
    SMART_RETAIL_DATABASE_PATH=/app/data/smart_retail.db \
    SMART_RETAIL_LOG_FILE_PATH=

WORKDIR /app

RUN groupadd --system smartretail \
    && useradd --system --gid smartretail --home-dir /app \
        --shell /usr/sbin/nologin smartretail

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir --parents /app/data \
    && chown --recursive smartretail:smartretail /app/data


FROM api-base AS test

USER root
RUN pip install --no-cache-dir ".[dev]"
COPY tests/integration/test_headless_service.py ./tests/integration/test_headless_service.py
USER smartretail

CMD ["python", "-m", "pytest", "tests/integration/test_headless_service.py", "-q", "-p", "no:cacheprovider"]


FROM api-base AS production

USER smartretail
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('SMART_RETAIL_API_PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)" || exit 1

CMD ["python", "-m", "smart_retail.api.service"]
