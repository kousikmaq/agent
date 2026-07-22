# ---------------------------------------------------------------------------
# Production Planning & Schedule Optimization Agent - Backend image
# Multi-stage build for a small, production-grade runtime image.
# ---------------------------------------------------------------------------

# --- Builder stage: install dependencies into a virtualenv ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create an isolated virtualenv we can copy to the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# --- Runtime stage: minimal image with only what we need to run ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as a non-root user for security.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# Bring in the pre-built virtualenv and application source.
COPY --from=builder /opt/venv /opt/venv
COPY . .

# Ensure runtime data directories exist and are owned by the app user.
RUN mkdir -p /app/datasets /app/outputs && chown -R app:app /app

USER app

EXPOSE 8000

# Container-level health check hitting the liveness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0) if urllib.request.urlopen('http://localhost:8000/api/v1/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
