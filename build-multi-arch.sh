#!/bin/bash

# Configuration
DOCKER_HUB_USERNAME="milangeorge"
IMAGE_NAME="qbittorrent-monitor"
IMAGE_TAG="latest"

echo "=== Building Multi-Arch qBittorrent Monitor Image ==="

# Login to Docker Hub
echo "1. Logging in to Docker Hub..."
if ! podman login docker.io; then
    echo "❌ Failed to login to Docker Hub"
    exit 1
fi

# Clean up existing images and manifests to avoid conflicts
echo "2. Cleaning up existing images and manifests..."
podman rmi -f ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} 2>/dev/null || true
podman rmi -f ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 2>/dev/null || true
podman rmi -f ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64 2>/dev/null || true
podman manifest rm ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} 2>/dev/null || true

# Build for x86_64 (amd64)
echo "3. Building for x86_64 (amd64) architecture..."
if ! podman build --platform linux/amd64 -t ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 .; then
    echo "❌ Failed to build x86_64 image"
    exit 1
fi

# Build for ARM64
echo "4. Building for ARM64 architecture..."
if ! podman build --platform linux/arm64 -t ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64 .; then
    echo "❌ Failed to build ARM64 image"
    exit 1
fi

# Push both images
echo "5. Pushing images to Docker Hub..."
if ! podman push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64; then
    echo "❌ Failed to push x86_64 image"
    exit 1
fi

if ! podman push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64; then
    echo "❌ Failed to push ARM64 image"
    exit 1
fi

# Create and push manifest using docker:// prefix to avoid local conflicts
echo "6. Creating and pushing multi-arch manifest..."
if podman manifest create ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
    docker://docker.io/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 \
    docker://docker.io/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64; then
    
    echo "7. Pushing manifest..."
    if podman manifest push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
        docker://docker.io/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}; then
        
        echo ""
        echo "✅ Successfully built and pushed multi-arch image!"
        echo "🔗 Image URL: docker.io/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"
        echo "   Supports: linux/amd64, linux/arm64"
        echo ""
        echo "🐳 To use with environment variables:"
        echo "   - Create a .env file with your qBittorrent configurations"
        echo "   - Use docker-compose.env.yml or set env vars directly"
    else
        echo "❌ Failed to push manifest"
        exit 1
    fi
else
    echo "❌ Failed to create manifest"
    exit 1
fi