# Stage 1: build frontend assets.
FROM node:22-alpine AS frontend-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY web/ ./
RUN npm run build

# Stage 2: runtime application.
FROM python:3.12-slim-bookworm

# Install runtime system dependencies. Keep apt lean for UAP build limits.
RUN apt-get update -o Acquire::Retries=3 && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV CLASSROOM_ANALYZER_PROJECT_ROOT=/app
ENV CLASSROOM_ANALYZER_DATA_DIR=/data

# pyproject builds need wheel/setuptools in the runtime image.
RUN pip install --no-cache-dir setuptools wheel

# Install the Python package.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Copy runtime config and prompt templates.
COPY config/ ./config/
COPY prompts/ ./prompts/

# Copy frontend build output.
COPY --from=frontend-builder /app/web/dist ./web/dist/

# UAP injects PORT. Fallback to 8080 for local container checks.
EXPOSE 8080

CMD ["sh", "-c", "uvicorn classroom_analyzer.server.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
