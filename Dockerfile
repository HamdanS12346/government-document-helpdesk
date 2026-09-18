# Backend Service Dockerfile
FROM python:3.11-slim AS base

# 1. Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata/

# 2. Install system dependencies for OCR, PDF rendering, and healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Cache Python dependencies in separate layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy application source code
COPY app/ ./app/
COPY guardrails/ ./guardrails/

# 5. Create non-root user for security
RUN useradd -m -u 1001 helpdesk && \
    chown -R helpdesk:helpdesk /app
USER helpdesk

EXPOSE 8000

# 6. Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# 7. Run FastAPI with Uvicorn bound to 0.0.0.0
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
