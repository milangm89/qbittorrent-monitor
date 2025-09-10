FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY qbittorrent_monitor_env.py .

# Create directories
RUN mkdir -p /app/logs

# Create non-root user (appuser)
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/logs"]

CMD ["python", "qbittorrent_monitor_env.py"]