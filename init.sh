#!/bin/bash

PIDS=()

if [ "$1" = "mobile" ]; then
    python3 shell2.py --mobile &
    PIDS+=($!)

    python3 labwc/mobile/status.py &
    PIDS+=($!)

    python3 labwc/mobile/home.py &
    PIDS+=($!)
else
    python3 shell2.py &
    PIDS+=($!)

    python3 labwc/desktop/taskbar.py &
    PIDS+=($!)
fi

cleanup() {
    echo "Stopping processes..."
    kill "${PIDS[@]}" 2>/dev/null
    wait "${PIDS[@]}" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait "${PIDS[@]}"