# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm

LABEL org.opencontainers.image.title="nikki4-webcheckin" \
      org.opencontainers.image.description="Daily check-in and reward redemption for the Nikki4 (閃耀暖暖) web event" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    ARTIFACTS_DIR=/app/artifacts \
    BROWSER=chrome \
    WEBDRIVER_PATH=/usr/bin/chromedriver

# Chromium + its driver give us real mobile emulation (viewport, DPR, touch).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-noto-cjk \
        fonts-liberation \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man /tmp/*

ENV TZ=Asia/Taipei

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY checkin.py ./

RUN useradd --create-home --uid 10001 runner \
    && mkdir -p "${ARTIFACTS_DIR}" \
    && chown -R runner:runner /app

USER runner

ENTRYPOINT ["python3", "checkin.py"]
