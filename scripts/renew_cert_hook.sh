#!/bin/bash
# Certbot deploy hook for TrendCrusher Dashboard

PROJECT_DIR="/Users/mudzizi/project/supertrend-trade"
PROJECT_CERT_DIR="$PROJECT_DIR/certs"
LE_DIR="/etc/letsencrypt/live/autotradehub.duckdns.org"

echo "[$(date)] Certbot Deploy Hook Triggered: Copying certificates..."

# Copy new certificates
mkdir -p "$PROJECT_CERT_DIR"
cp "$LE_DIR/fullchain.pem" "$PROJECT_CERT_DIR/"
cp "$LE_DIR/privkey.pem" "$PROJECT_CERT_DIR/"
chown -R mudzizi:staff "$PROJECT_CERT_DIR"

echo "[$(date)] Restarting TrendCrusher Dashboard to apply new certificates..."

# Find and kill the process running on port 5000
PID=$(lsof -t -i :5000)
if [ ! -z "$PID" ]; then
    echo "Killing process on port 5000 (PID: $PID)"
    kill -9 $PID
    sleep 2
fi

# Restart dashboard in the background using the virtual environment python
cd "$PROJECT_DIR"
nohup ./venv/bin/python scripts/dashboard.py > dashboard.log 2>&1 &

echo "[$(date)] Dashboard restarted successfully."
