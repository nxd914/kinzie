FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV L2_JSONL_OUTPUT_DIR=/app/data/l2

RUN mkdir -p /app/data/l2

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD test -d /app/data/l2 || exit 1

CMD ["python3", "-m", "strategies.crypto.daemon"]
