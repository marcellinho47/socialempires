FROM python:3.11-slim

WORKDIR /app

# Small deps (curl for HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY order: least-likely-to-change → most-likely-to-change.
# Each COPY is its own layer so code-only commits skip the heavy assets
# layer entirely (and `docker compose build socialempires` goes from
# ~60s to a few seconds).
COPY stub/ ./stub/
COPY assets/ ./assets/
COPY config/ ./config/
COPY mods/ ./mods/
COPY villages/ ./villages/
COPY templates/ ./templates/
# Python sources change most often — keep last
COPY *.py ./

ENV SE_HOST=0.0.0.0 \
    SE_PORT=5050 \
    PYTHONUNBUFFERED=1

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${SE_PORT}/" > /dev/null || exit 1

CMD ["python", "server.py"]
