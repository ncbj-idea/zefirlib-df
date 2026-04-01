#!/usr/bin/env bash
set -e

detect_platform() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "mac"
    else
        echo "other"
    fi
}

setup_mac() {
    echo ">>> macOS detected"
    # Check XQuartz is installed
    if ! [ -d "/Applications/Utilities/XQuartz.app" ] && ! [ -d "$HOME/Applications/XQuartz.app" ]; then
        echo "  XQuartz is not installed."
        echo "  To install XQuartz, run:"
        echo "    brew install --cask xquartz"
        exit 1
    fi
    # Check XQuartz is running
    if ! pgrep -x Xquartz > /dev/null; then
        echo "  Starting XQuartz..."
        open -a XQuartz
        sleep 3
    fi
    # Allow Docker to connect over network
    # Use local XQuartz display (:0) for xhost, then set container display
    DISPLAY=:0 /opt/X11/bin/xhost +
    export DISPLAY=host.docker.internal:0
}

# Get current user UID and GID for Docker
HOST_UID=$(id -u)
HOST_GID=$(id -g)

echo ">>> Using HOST_UID=$HOST_UID HOST_GID=$HOST_GID"

PLATFORM=$(detect_platform)
if [ "$PLATFORM" = "mac" ]; then
    setup_mac
fi

HOST_UID=$HOST_UID HOST_GID=$HOST_GID docker compose up gui
