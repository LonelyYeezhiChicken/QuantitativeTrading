# ==============================================================================
# Crypto AI Quantitative Trading Platform - Production Dockerfile
# Optimized for lightweight 24/7 cloud deployment (AWS Lightsail, VPS, etc.)
# ==============================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Taipei

WORKDIR /app

# Install system dependencies (tzdata for Asia/Taipei, curl for healthcheck, libgomp1 for LightGBM)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    git \
    libgomp1 \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install uv for ultra-fast Python package resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project specification first for layer caching
COPY pyproject.toml .

# Install dependencies into system environment
RUN uv pip install --system --no-cache -e .

# Copy application code
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/data /app/journals /app/logs

# Default entrypoint runs interactive menu or can be overridden by docker-compose
CMD ["python", "-u", "apps/cli/autopilot.py", "--symbol", "BTC/USDT", "--leverage", "3", "--capital", "200", "--arm", "--run-loop", "--live", "--interval", "60"]
