FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY config.production.yaml ./
RUN pip install --no-cache-dir -e .

CMD ["profiru-watch"]
