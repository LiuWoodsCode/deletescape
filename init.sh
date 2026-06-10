#!/bin/bash

python3 shell2.py &
PID1=$!

python3 labwc/desktop/taskbar.py &
PID2=$!

cleanup() {
    echo "Stopping processes..."
    kill "$PID1" "$PID2" 2>/dev/null
    wait "$PID1" "$PID2" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait "$PID1" "$PID2"