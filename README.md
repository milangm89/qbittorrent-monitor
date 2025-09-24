# qBittorrent Multi-Instance Monitor

[![Docker](https://img.shields.io/badge/Docker-Multi--Arch-blue?logo=docker)](https://hub.docker.com/r/milangeorge/qbittorrent-monitor)
[![Python](https://img.shields.io/badge/Python-3.9-green?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Docker container that monitors multiple qBittorrent instances and automatically cleans torrent names by removing unwanted domain names, advertisements, and tracker information from torrent titles, folders, and filenames.

## ✨ Features

### 🔧 Core Functionality
- **Multi-Instance Support**: Monitor unlimited qBittorrent instances simultaneously
- **Intelligent Domain Removal**: Advanced pattern matching to identify and remove:
  - Domain names (e.g., `example.com`, `tracker.site`)
  - URLs with protocols (`http://`, `https://`)
  - Common tracker suffixes (`.com`, `.org`, `.net`, `.tv`, `.io`, etc.)
- **File & Folder Renaming**: Clean both torrent names and file/folder structures
- **Extension Preservation**: Maintains file extensions during renaming
- **Real-time Monitoring**: Continuous monitoring with configurable intervals

### 🏗️ Technical Features  
- **Multi-Architecture Support**: Compatible with x86_64 (amd64) and ARM64 platforms
- **Security**: Runs as non-root user with configurable UID/GID
- **Robust Error Handling**: Exponential backoff retry logic for network failures
- **Connection Timeout Management**: Configurable timeouts and retry strategies
- **Comprehensive Logging**: Detailed logs with rotation support
- **Docker Compose Ready**: Easy deployment with environment variables

### 🎯 Smart Cleaning Logic
- Preserves important parts of filenames while removing tracker junk
- Handles edge cases like empty names after cleaning
- Supports both files and folders with different cleaning strategies
- Non-destructive: Only renames when domains/URLs are detected

## 🚀 Quick Start

### Method 1: Docker Compose (Recommended)
```bash
# Download the docker-compose.yml
curl -o docker-compose.yml https://raw.githubusercontent.com/milangm89/qbittorrent-monitor/main/docker-compose.yml

# Edit the configuration
nano docker-compose.yml

# Start the container
docker-compose up -d
```

### Method 2: Direct Docker Run
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
```

## ⚙️ Configuration

### Environment Variables

Each qBittorrent instance requires a set of environment variables with a numeric suffix (0, 1, 2, etc.):

#### Required Variables
| Variable | Description | Example |
|----------|-------------|---------|
| `QBITTORRENT_X_NAME` | Friendly name for the instance | `main`, `seedbox` |
| `QBITTORRENT_X_URL` | qBittorrent Web UI URL | `http://192.168.1.100:8080` |
| `QBITTORRENT_X_USERNAME` | Web UI username | `admin` |
| `QBITTORRENT_X_PASSWORD` | Web UI password | `adminadmin` |

#### Optional Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `QBITTORRENT_X_CHECK_INTERVAL` | `30` | Check interval in seconds |
| `QBITTORRENT_X_CONNECTION_TIMEOUT` | `30` | HTTP timeout in seconds |
| `QBITTORRENT_X_MAX_RETRIES` | `5` | Maximum retry attempts |
| `QBITTORRENT_X_RETRY_DELAY` | `10` | Delay between retries (seconds) |
| `QBITTORRENT_X_FOLDER_RETRY_DELAY` | `30` | Extended delay for folder operations |

### Example Multi-Instance Configuration
```yaml
environment:
  # First instance
  - QBITTORRENT_0_NAME=main
  - QBITTORRENT_0_URL=http://192.168.1.100:8080
  - QBITTORRENT_0_USERNAME=admin
  - QBITTORRENT_0_PASSWORD=adminadmin
  - QBITTORRENT_0_CHECK_INTERVAL=30
  
  # Second instance  
  - QBITTORRENT_1_NAME=seedbox
  - QBITTORRENT_1_URL=http://seedbox.example.com:8080
  - QBITTORRENT_1_USERNAME=user
  - QBITTORRENT_1_PASSWORD=password
  - QBITTORRENT_1_CHECK_INTERVAL=60
  
  # Global settings
  - TZ=America/New_York
```

## 📂 Directory Structure

```
qbittorrent-monitor/
├── Dockerfile                    # Container definition
├── docker-compose.yml          # Compose configuration
├── build-multi-arch.sh         # Multi-arch build script
├── qbittorrent_multi_monitor.py # Main application
├── requirements.txt             # Python dependencies
├── logs/                        # Log files (volume mount)
└── README.md                    # This file
```

## 🔧 Advanced Usage

### Custom User ID/Group ID
For TrueNAS, Unraid, or other systems requiring specific user permissions:

```bash
docker run -d \
  --name qbittorrent-monitor \
  --user 1001:1001 \
  # ... other options
```

### Log Management
The container writes logs to `/app/logs/qbittorrent_monitor.log`. Mount this directory to persist logs:

```yaml
volumes:
  - ./logs:/app/logs
  
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

### Building Custom Image
```bash
# Clone the repository
git clone https://github.com/milangm89/qbittorrent-monitor.git
cd qbittorrent-monitor

# Build for current architecture
docker build -t qbittorrent-monitor .

# Build for multiple architectures (requires podman)
chmod +x build-multi-arch.sh
./build-multi-arch.sh
```

## 🔍 How It Works

1. **Connection**: Establishes authenticated sessions with configured qBittorrent instances
2. **Monitoring**: Continuously polls for torrent status changes
3. **Analysis**: Scans torrent names, folders, and files for domain patterns using regex
4. **Cleaning**: Removes identified domains while preserving file extensions and important content
5. **Renaming**: Applies clean names via qBittorrent API
6. **Logging**: Records all actions and errors for monitoring

### Supported Domain Patterns
- Full URLs: `https://tracker.example.com/announce`
- Domain names: `tracker.site`, `www.example.org`
- Common TLDs: `.com`, `.org`, `.net`, `.tv`, `.io`, `.co`, `.uk`, `.de`, `.fr`, etc.
- Special handling for legitimate content that shouldn't be renamed

## 🐛 Troubleshooting

### Common Issues

**Connection Refused**
```
[main] Connection error when connecting to http://192.168.1.100:8080
```
- Verify qBittorrent Web UI is enabled and accessible
- Check firewall settings and network connectivity
- Confirm the correct IP address and port

**Authentication Failed**
```
[main] Failed to login to qBittorrent: Fails.
```
- Verify username and password are correct
- Check if Web UI authentication is enabled in qBittorrent settings

**Permission Denied (File Operations)**
```
Error renaming folder: [Errno 13] Permission denied
```
- Ensure the container user has appropriate permissions
- Check file system permissions on the download directory
- Verify UID/GID mapping is correct

### Debug Mode
To increase logging verbosity, modify the Python script or add debug environment variables.

### Health Monitoring
Check container logs:
```bash
docker logs qbittorrent-monitor
docker logs -f qbittorrent-monitor  # Follow mode
```

## 📋 Requirements

### qBittorrent Requirements
- qBittorrent v4.1.0 or newer
- Web UI enabled with authentication
- Network access from the container to qBittorrent instances

### System Requirements
- Docker or Podman
- 50MB available storage (for image and logs)
- Network connectivity to qBittorrent instances
- Minimal CPU/RAM usage (Python 3.9 slim base)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`  
3. Make your changes and test thoroughly
4. Commit with descriptive messages: `git commit -m "Add feature X"`
5. Push to your branch: `git push origin feature-name`
6. Submit a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- **Docker Hub**: [milangeorge/qbittorrent-monitor](https://hub.docker.com/r/milangeorge/qbittorrent-monitor)
- **GitHub**: [milangm89/qbittorrent-monitor](https://github.com/milangm89/qbittorrent-monitor)
- **Issues**: [Report bugs or request features](https://github.com/milangm89/qbittorrent-monitor/issues)

## ⭐ Support

If this project helps you, please consider giving it a star on GitHub! It helps others discover the project and motivates continued development.

For questions, issues, or feature requests, please use the GitHub Issues page.