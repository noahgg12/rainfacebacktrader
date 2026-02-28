#!/bin/bash
# ============================================================================
# Rainface Backtrader Service Installer
# Sets up the backtesting server to run automatically on macOS.
# ============================================================================

set -e

PROJECT_DIR="/Users/noah123/rainfacebacktrader"
PLIST_NAME="com.rainface.backtrader.plist"
PLIST_SRC="$PROJECT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🔧 Rainface Backtrader Service Installer"
echo "========================================="

# 1. Create logs directory
echo "📁 Creating logs directory..."
mkdir -p "$PROJECT_DIR/logs"

# 2. Install Python dependencies
echo "📦 Installing Python dependencies..."
source "$PROJECT_DIR/.venv/bin/activate"
pip install -r "$PROJECT_DIR/requirements.txt"

# 3. Stop existing service (if running)
echo "🛑 Stopping existing service (if any)..."
launchctl unload "$PLIST_DST" 2>/dev/null || true

# 4. Copy plist to LaunchAgents
echo "📋 Installing launchd service..."
cp "$PLIST_SRC" "$PLIST_DST"

# 5. Load the service
echo "🚀 Starting service..."
launchctl load "$PLIST_DST"

# 6. Wait a moment and check
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
