# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Run stage
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY config.example.yml ./config.yml

# Create dedicated non-root user for security
RUN groupadd -g 10001 opsgroup && useradd -u 10001 -g opsgroup -m opsuser

RUN mkdir -p /home/opsuser/.aws /home/opsuser/.kube \
    && chown -R opsuser:opsgroup /home/opsuser

USER opsuser

ENTRYPOINT ["opsagents"]
CMD ["--help"]
