#!/bin/bash
# ============================================================================
# Rainface Backtrader Service Installer
# Supports Docker (preferred) or fallback to macOS launchd.
# ============================================================================

set -e

PROJECT_DIR="/Users/noah123/rainfacebacktrader"
PLIST_NAME="com.rainface.backtrader.plist"
PLIST_SRC="$PROJECT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🔧 Rainface Backtrader Service Installer"
echo "========================================="

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# ---------------------------------------------------------------------------
# Check if Docker is available
# ---------------------------------------------------------------------------
if command -v docker &> /dev/null && docker info &> /dev/null; then
    echo "🐳 Docker detected — using Docker setup"
    echo ""

    # Step 1: Build the main server image
    echo "📦 Building server image..."
    docker compose -f "$PROJECT_DIR/docker-compose.yml" build
    echo "   ✅ Server image built"
    echo ""

    # Step 2: Build the sandbox image for custom strategies
    echo "🔒 Building sandbox image..."
    docker build -f "$PROJECT_DIR/Dockerfile.sandbox" -t rainface-sandbox:latest "$PROJECT_DIR"
    echo "   ✅ Sandbox image built"
    echo ""

    # Step 3: Stop any existing launchd service
    echo "🛑 Stopping existing launchd service (if any)..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true

    # Step 4: Start with Docker Compose
    echo "🚀 Starting server with Docker Compose..."
    docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d
    echo ""

    # Step 5: Wait and check
    sleep 3
    if curl -s http://localhost:8420/health > /dev/null 2>&1; then
        echo "🟢 Server is running at http://localhost:8420"
        echo ""
        curl -s http://localhost:8420/health | python3 -m json.tool
    else
        echo "🟡 Server is starting up, give it a few seconds..."
        echo "   Check logs: docker compose -f $PROJECT_DIR/docker-compose.yml logs -f"
    fi

    echo ""
    echo "========================================="
    echo "📌 Docker commands:"
    echo "   Check status:  curl http://localhost:8420/health"
    echo "   View logs:     docker compose -f $PROJECT_DIR/docker-compose.yml logs -f"
    echo "   Stop service:  docker compose -f $PROJECT_DIR/docker-compose.yml down"
    echo "   Start service: docker compose -f $PROJECT_DIR/docker-compose.yml up -d"
    echo "   Rebuild:       docker compose -f $PROJECT_DIR/docker-compose.yml build"
    echo "========================================="

else
    echo "⚠️  Docker not found — falling back to macOS launchd"
    echo ""

    # Install Python dependencies
    echo "📦 Installing Python dependencies..."
    source "$PROJECT_DIR/.venv/bin/activate"
    pip install -r "$PROJECT_DIR/requirements.txt"

    # Stop existing service (if running)
    echo "🛑 Stopping existing service (if any)..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true

    # Copy plist to LaunchAgents
    echo "📋 Installing launchd service..."
    cp "$PLIST_SRC" "$PLIST_DST"

    # Load the service
    echo "🚀 Starting service..."
    launchctl load "$PLIST_DST"

    # Wait a moment and check
    sleep 2
    echo ""
    echo "✅ Service installed! Checking status..."
    echo ""

    if curl -s http://localhost:8420/health > /dev/null 2>&1; then
        echo "🟢 Server is running at http://localhost:8420"
        echo ""
        curl -s http://localhost:8420/health | python3 -m json.tool
    else
        echo "🟡 Server is starting up, give it a few seconds..."
        echo "   Check logs at: $PROJECT_DIR/logs/backtrader.log"
        echo "   Check errors at: $PROJECT_DIR/logs/backtrader-error.log"
    fi

    echo ""
    echo "========================================="
    echo "📌 Useful commands:"
    echo "   Check status:  curl http://localhost:8420/health"
    echo "   View logs:     tail -f $PROJECT_DIR/logs/backtrader.log"
    echo "   Stop service:  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
    echo "   Start service: launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
    echo "========================================="
fi
