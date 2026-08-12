# Local-only Phase 3 Dockerfile. The ignored detector model must be supplied
# in the local build context; no public deployment is supported by this phase.
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV DETECTOR_MODEL_PATH=/app/models/day4/best.onnx

WORKDIR /app

# Install system dependencies required by OpenCV and RapidOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt-get/lists/*

# Copy the tracked production dependency definition.
COPY backend/requirements.txt /app/requirements.txt

# Install only the explicitly pinned production requirements. Build failures
# are intentionally not masked by an unpinned fallback installation.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source code
COPY backend/app /app/app

# The model is ignored by Git and is a required local build prerequisite.
COPY models/day4/best.onnx /app/models/day4/best.onnx
RUN test "$(stat -c '%s' /app/models/day4/best.onnx)" = "12265233" \
    && test "$(sha256sum /app/models/day4/best.onnx | cut -d' ' -f1)" = "a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9"

# Create non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck remains independent of model/database initialization.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Bind inside the container; publish it to loopback on the host, for example:
# 127.0.0.1:8000:8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
