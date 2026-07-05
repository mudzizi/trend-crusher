#!/usr/bin/env bash
# restart_all.sh: Restarts TrendCrusher Bot (via Watchdog) and Dashboard

# Dynamically resolve the project root directory based on the script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( dirname "$SCRIPT_DIR" )"

cd "$PROJECT_DIR"

echo "[$(date)] 🛑 Stopping existing processes..."

# Find and kill watchdog, live_bot_async, and dashboard
processes=("scripts/watchdog.py" "scripts/live_bot_async.py" "scripts/dashboard.py")

for proc in "${processes[@]}"; do
    PID=$(pgrep -f "$proc")
    if [ ! -z "$PID" ]; then
        echo "Killing $proc (PID: $PID)..."
        kill -9 $PID
        sleep 1
    fi
done

echo "[$(date)] 🚀 Starting processes..."

# Ensure we use the virtual environment python
PYTHON_BIN="./venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    # Fallback to system python if venv is not found
    PYTHON_BIN="python3"
fi

# Ensure log directory exists
mkdir -p log

# Start Watchdog (which monitors and runs live_bot_async.py)
echo "Starting Watchdog..."
nohup $PYTHON_BIN scripts/watchdog.py > watchdog.log 2>&1 &

# Start Dashboard
echo "Starting Dashboard..."
nohup $PYTHON_BIN scripts/dashboard.py > dashboard.log 2>&1 &

echo "[$(date)] ✅ TrendCrusher Bot and Dashboard restarted successfully."
