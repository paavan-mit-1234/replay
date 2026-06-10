# Production image for the Replay API. Host-agnostic (Render, Fly.io, Oracle,
# Railway, etc.). Binds to $PORT, which hosts inject. All configuration comes
# from environment variables; no .env is baked in.
FROM python:3.12-slim

WORKDIR /app

# Install runtime deps first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PORT=8000
EXPOSE 8000

# One worker is plenty for the free tier; scale with $WEB_CONCURRENCY later.
CMD ["sh", "-c", "uvicorn replay.api.app:app --host 0.0.0.0 --port ${PORT}"]
