# qBittorrent Multi-Instance Monitor

A Docker container that monitors multiple qBittorrent instances and automatically renames torrents and files to remove domain names.

## Features

- Monitor multiple qBittorrent instances simultaneously via environment variables
- Automatically remove domain names from torrent titles, folders, and filenames
- Multi-architecture support (x86_64 and ARM64)
- Runs as non-root user (appuser) with configurable UID/GID
- Persistent logging
- Retry logic for failed operations
- Docker Compose ready with environment variable support

## Quick Start

### Method 1: Direct Environment Variables
```bash
docker run -d \
  --name qbittorrent-monitor \
  --user 1001:1001 \
  -e QBITTORRENT_0_NAME=main \
  -e QBITTORRENT_0_URL=http://192.168.1.100:8080 \
  -e QBITTORRENT_0_USERNAME=admin \
  -e QBITTORRENT_0_PASSWORD=adminadmin \
  -v ./logs:/app/logs \
  milangeorge/qbittorrent-monitor:latest