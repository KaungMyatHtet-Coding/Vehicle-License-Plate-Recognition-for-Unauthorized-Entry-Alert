# Day 19 Production Dockerfile for Render / Container deployment
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system dependencies required by OpenCV and RapidOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt-get/lists/*

# Copy dependency definition
COPY backend/pyproject.toml backend/requirements.txt* /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    pydantic \
    pydantic-settings \
    opencv-python-headless \
    rapidocr-onnxruntime \
    onnxruntime \
    numpy \
    python-multipart \
    pillow

# Copy application source code
COPY backend/app /app/app

# Copy model artifacts into place
COPY models /app/models

# Create non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck for Render / Railway
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start FastAPI using uvicorn binding to 0.0.0.0 and dynamic $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
