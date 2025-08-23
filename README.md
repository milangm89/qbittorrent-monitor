# qBittorrent Multi-Instance Monitor

A Docker container that monitors multiple qBittorrent instances and automatically renames torrents and files to remove domain names.

## Features

- Monitor multiple qBittorrent instances simultaneously
- Automatically remove domain names from torrent titles, folders, and filenames
- Multi-architecture support (x86_64 and ARM64)
- Runs as non-root user (appuser) with configurable UID/GID
- Persistent logging and configuration
- Retry logic for failed operations
- Docker Compose ready

## Quick Start

1. Clone this repository
2. Edit `config/config.json` with your qBittorrent instances
3. Run with Docker Compose:
   ```bash
   docker-compose up -d