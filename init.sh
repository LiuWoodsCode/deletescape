#!/bin/bash

if [ "$1" = "mobile" ]; then
    python3 shell2.py --mobile &
    PID1=$!

    python3 labwc/mobile/status.py &
    PID2=$!
else
    python3 shell2.py &
    PID1=$!

    python3 labwc/desktop/taskbar.py &
    PID2=$!
fi

cleanup() {
    echo "Stopping processes..."
    kill "$PID1" "$PID2" 2>/dev/null
    wait "$PID1" "$PID2" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait "$PID1" "$PID2"