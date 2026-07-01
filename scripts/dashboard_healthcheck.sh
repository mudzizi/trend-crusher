#!/usr/bin/env bash
# Dashboard Healthcheck & Watchdog Script

# Target URL to check
URL_HTTPS="https://127.0.0.1:5000/login"
URL_HTTP="http://127.0.0.1:5000/login"

# Dynamically resolve the project root directory based on the script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( dirname "$SCRIPT_DIR" )"

# Ensure the log directory exists
mkdir -p "$PROJECT_DIR/log"

# Perform curl check (5s connect timeout, 10s total timeout, quiet mode)
# Checks both HTTPS (with self-signed cert permission -k) and HTTP
if ! curl -sk --max-time 10 "$URL_HTTPS" > /dev/null && ! curl -s --max-time 10 "$URL_HTTP" > /dev/null; then
    echo "[$(date)] 🚨 Dashboard healthcheck failed! Attempting restart..." >> "$PROJECT_DIR/log/healthcheck.log"
    
    # Find dashboard.py process using pgrep and kill it
    PID=$(pgrep -f "scripts/dashboard.py")
    if [ ! -z "$PID" ]; then
        echo "[$(date)] Killing unresponsive process (PID: $PID)" >> "$PROJECT_DIR/log/healthcheck.log"
        kill -9 $PID
        sleep 2
    fi
    
    # Start the dashboard process in the background using the virtual environment python
    cd "$PROJECT_DIR"
    nohup ./venv/bin/python scripts/dashboard.py > dashboard.log 2>&1 &
    
    echo "[$(date)] ✅ Dashboard restarted successfully." >> "$PROJECT_DIR/log/healthcheck.log"
else
    # Success logs (uncomment if verbose logging is desired)
    # echo "[$(date)] Dashboard is healthy." >> "$PROJECT_DIR/log/healthcheck.log"
    echo "Dashboard is healthy."
fi
