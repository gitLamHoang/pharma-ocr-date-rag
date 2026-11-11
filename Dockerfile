# Stage 1: build the frontend.
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the API with Tesseract, serving the built frontend at /.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
# English only: tesseract-ocr ships the eng pack.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv \
    DATA_DIR=/app/data PATH=/app/.venv/bin:$PATH
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/pharma_dates ./pharma_dates
RUN uv sync --frozen --no-dev
COPY --from=web /app/frontend/dist /app/frontend/dist

RUN useradd --uid 1000 --create-home app && mkdir -p /app/data && chown app /app/data
USER app
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "--factory", "pharma_dates.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
