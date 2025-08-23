#!/bin/bash

# Set your Docker Hub username
DOCKER_HUB_USERNAME="dockerhubuser"
IMAGE_NAME="qbittorrent-monitor"
IMAGE_TAG="latest"

# Login to Docker Hub
echo "Logging in to Docker Hub..."
podman login docker.io

# Build for x86_64 (amd64) architecture
echo "Building for x86_64 (amd64) architecture..."
podman build \
  --platform linux/amd64 \
  -t ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 \
  --no-cache \
  .

# Push the x86_64 image
echo "Pushing x86_64 image..."
podman push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64

# Optional: Build for ARM64 as well (for completeness)
echo "Building for ARM64 architecture..."
podman build \
  --platform linux/arm64 \
  -t ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64 \
  --no-cache \
  .

# Push the ARM64 image
echo "Pushing ARM64 image..."
podman push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64

# Create and push manifest for multi-arch support
echo "Creating multi-arch manifest..."
podman manifest create ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
  ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 \
  ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64

# Annotate architectures
podman manifest annotate ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
  ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-amd64 --arch amd64

podman manifest annotate ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
  ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}-arm64 --arch arm64

# Push the manifest
echo "Pushing multi-arch manifest..."
podman manifest push ${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG} \
  docker://${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}

echo "Build and push completed!"
echo "Image available at: docker.io/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"