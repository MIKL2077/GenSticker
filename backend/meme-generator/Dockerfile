# Build from repository root: docker build -f backend/meme-generator/Dockerfile .
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fontconfig fonts-noto-cjk fonts-noto-color-emoji libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --home-dir /home/gensticker gensticker
COPY backend/pil-utils /app/backend/pil-utils
COPY backend/meme-generator /app/backend/meme-generator
COPY deploy/requirements-features.txt /app/deploy/requirements-features.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e /app/backend/meme-generator -r /app/deploy/requirements-features.txt \
    && mkdir /data /models && chown gensticker:gensticker /data /models
ENV GENSTICKER_STATE_DIR=/data U2NET_HOME=/models PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HOME=/home/gensticker
USER gensticker
WORKDIR /app/backend/meme-generator
VOLUME ["/data", "/models"]
EXPOSE 3001
CMD ["python", "-m", "uvicorn", "meme_generator.app:app", "--host", "0.0.0.0", "--port", "3001", "--workers", "1", "--limit-concurrency", "24"]
