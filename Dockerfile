# Dockerfile for SMG Bot
FROM python:3.9-slim

# Set timezone
ENV TZ=Europe/Budapest
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install runtime system tools
RUN apt-get update && apt-get install -y --no-install-recommends     procps     && rm -rf /var/lib/apt/lists/*

# Install dependencies first for Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY smg_bot/ /app/smg_bot/
COPY .env.example /app/.env.example

# Create directory for runtime logs
RUN mkdir -p /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1     LOGS_DIR=/app/logs     APP_DIR=/app

# Healthcheck script
RUN echo '#!/bin/sh\n\
if ! ps aux | grep -v grep | grep -E "smg_bot" > /dev/null; then\n\
  echo "Bot process not running!"\n\
  exit 1\n\
fi\n\
if [ ! -f /app/logs/steamgifts_bot.log ]; then\n\
  echo "Log file does not exist!"\n\
  exit 1\n\
fi\n\
LAST_MODIFIED=$(stat -c %Y /app/logs/steamgifts_bot.log 2>/dev/null || echo 0)\n\
NOW=$(date +%s)\n\
AGE=$((NOW - LAST_MODIFIED))\n\
if [ $AGE -gt 1800 ]; then\n\
  echo "No log activity in the last 30 minutes!"\n\
  exit 1\n\
fi\n\
echo "Health check passed"\n\
exit 0' > /app/healthcheck.sh && chmod +x /app/healthcheck.sh

HEALTHCHECK --interval=5m --timeout=30s --start-period=5m --retries=3     CMD /app/healthcheck.sh

# Run the modernized bot package
CMD ["python", "-u", "-m", "smg_bot.main"]
