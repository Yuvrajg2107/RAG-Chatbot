FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data MODEL_CACHE_DIR=/app/.cache/models
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.7 \
    && useradd --create-home --uid 10001 margin \
    && mkdir -p /app/data /app/.cache \
    && chown -R margin:margin /app/data /app/.cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY static ./static
COPY samples ./samples
USER margin
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
