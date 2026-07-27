# Backend image. Data CSVs are shipped in the repo; models are trained at BUILD time so the
# container starts instantly at runtime. Provide the Azure key at runtime via -e.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./

# Train models into the image (data is already present). Runtime start is then instant.
RUN python -m app.setup

# Models exist in the image, so no auto-setup needed at runtime.
ENV AUTO_SETUP=0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
