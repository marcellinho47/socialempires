FROM python:3.11-slim

WORKDIR /app

# Deps só com o que o pip/SSL precisa (curl pra healthcheck opcional)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Instala deps primeiro (melhor cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código — saves/ e download_assets/ são bind mounts em runtime
COPY . .

# Default envs (sobrescrevíveis pelo compose)
ENV SE_HOST=0.0.0.0 \
    SE_PORT=5050 \
    PYTHONUNBUFFERED=1

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${SE_PORT}/" > /dev/null || exit 1

CMD ["python", "server.py"]
