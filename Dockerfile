# =============================================================================
# Rainface Backtrader API Server — Production Image
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): install Python deps into an isolated venv
#   Stage 2 (runtime): slim image with just the venv + app code
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for any C-extension deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Create a venv and install deps
RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2 — Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy the pre-built venv from builder
COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY backtrader/ /app/backtrader/
COPY strategies/ /app/strategies/
COPY server.py /app/server.py
COPY sandbox_runner.py /app/sandbox_runner.py

# Install Docker CLI so server.py can launch sandbox containers
# Only the CLI is needed — the daemon runs on the host via the mounted socket
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Create directories for data and logs
RUN mkdir -p /app/datas /app/logs

# Default port — can override with RAINFACE_BT_PORT env var
ENV RAINFACE_BT_PORT=8420
EXPOSE 8420

CMD ["python", "server.py"]
