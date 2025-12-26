# ============================================
# Fudly Bot - Production Dockerfile
# Multi-stage build for smaller image size
# ============================================

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim AS runtime

# Labels for image metadata
LABEL maintainer="Fudly Team <support@fudly.uz>"
LABEL version="2.0.0"
LABEL description="Fudly Telegram Bot - Food rescue platform"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd -r botuser && useradd -r -g botuser -u 1000 botuser

# Copy application code (includes webapp/partner-panel/)
COPY --chown=botuser:botuser . .

# Remove unnecessary files
RUN rm -rf tests/ htmlcov/ .git/ .pytest_cache/ __pycache__/ \
    *.md docs/ load_tests/ scripts/ .env.example .pre-commit-config.yaml \
    2>/dev/null || true

# Switch to non-root user
USER botuser

# Expose port for health checks
EXPOSE 8080

# Health check - use curl for reliability
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Default command
CMD ["python", "bot.py"]
