#!/bin/bash
set -e

PROFILE_ID=${PROFILE_ID:-acme-saas}
CONNECTOR=${CONNECTOR:-csv}

echo "Forecast Tieout starting..."
echo "Profile: $PROFILE_ID"
echo "Connector: $CONNECTOR"

# Copy snapshot data to served directory
mkdir -p /app/frontend/dist/data/profiles/$PROFILE_ID
if [ -f "/app/engine/data/$PROFILE_ID/snapshot.json" ]; then
    cp /app/engine/data/$PROFILE_ID/snapshot.json /app/frontend/dist/data/profiles/$PROFILE_ID/
    echo "Snapshot loaded from engine/data/$PROFILE_ID/"
elif [ -f "/app/frontend/dist/data/profiles/$PROFILE_ID/snapshot.json" ]; then
    echo "Using pre-built snapshot"
else
    echo "Warning: No snapshot found. Generate one with:"
    echo "  python -m engine.scripts.generate_snapshot --profile $PROFILE_ID"
fi

# Start nginx
echo "Starting nginx on port 8080..."
exec nginx -g "daemon off;"
