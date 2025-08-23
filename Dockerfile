FROM --platform=$TARGETPLATFORM python:3.9-slim

ARG TARGETPLATFORM
ARG BUILDPLATFORM

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY qbittorrent_multi_monitor.py .

# Create directories
RUN mkdir -p /app/logs /app/config

# Create default config if it doesn't exist
RUN echo '{"instances": []}' > /app/config/config.json

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
RUN chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/logs", "/app/config"]

CMD ["python", "qbittorrent_multi_monitor.py"]