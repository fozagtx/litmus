# ── Stage 1: frontend build ─────────────────────────────────────────────────
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ server/
COPY scripts/ scripts/
COPY --from=web /app/web/dist web/dist
RUN mkdir -p data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
