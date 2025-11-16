FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check: checks /health from webhook or polling health server
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=5 \
    CMD python -c "import os,sys; from urllib.request import urlopen; port=(os.environ.get('POLLING_HEALTH_PORT') or os.environ.get('PORT','8080')); url=f'http://127.0.0.1:{port}/health';\nimport urllib.error, socket;\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n;\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n;\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n;\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n;\n\n\n\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n\n\n;\n\n\n;\n\n\n;\n\n\n\n\n;\ntry:\n    r=urlopen(url, timeout=5)\n    sys.exit(0 if getattr(r, 'status', 200)==200 else 1)\nexcept Exception:\n    sys.exit(1)"

# Run bot
CMD ["python", "bot.py"]
