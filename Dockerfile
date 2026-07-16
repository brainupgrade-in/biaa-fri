# Single-image build: React bundle + FastAPI + embedded Chroma + SQLite.
# Runs as one process (uvicorn) on port 8000 with state under /data.

FROM node:20-alpine AS frontend

WORKDIR /build

COPY frontend/package.json ./
RUN npm install

COPY frontend/tsconfig.json ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build


# Python deps are built in a throwaway stage: chroma-hnswlib ships no cp312
# wheel and needs a C++ compiler, but nothing needs one at runtime. Only the
# resulting venv is carried into the final image.
FROM python:3.12-slim AS pydeps

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim

WORKDIR /app

COPY --from=pydeps /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    STATIC_DIR=/app/frontend/build \
    DATABASE_URL=sqlite:////data/app.db \
    CHROMA_PERSIST_DIR=/data/chroma_db \
    CHROMA_EMBEDDED=true \
    ANONYMIZED_TELEMETRY=False

# High uid to avoid colliding with a host user: RLIMIT_NPROC is enforced
# per-uid across the host, so uid 1000 shares the desktop user's budget.
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

# Bake Chroma's embedding model (~80MB ONNX) into the image. Without this the
# first upload downloads it at runtime, which stalls the request for minutes and
# fails outright with no egress. Runs as appuser so it lands in the HOME cache
# the app reads at runtime.
RUN python -c "from chromadb.utils import embedding_functions; embedding_functions.ONNXMiniLM_L6_V2()(['warmup'])"

COPY --chown=appuser:appuser ./backend ./backend
COPY --chown=appuser:appuser ./shared ./shared
COPY --from=frontend --chown=appuser:appuser /build/build ./frontend/build

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

# Single worker: main._audit_log is per-process, so extra workers would each
# keep their own guardrail log. The default SQLite file would also serialise
# writes across them.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
