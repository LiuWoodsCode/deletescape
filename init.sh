#!/bin/bash

PIDS=()

setup_needed() {
    python3 -c 'import json, sys
try:
    with open("config.json", "r", encoding="utf-8") as handle:
        config = json.load(handle)
except Exception:
    sys.exit(0)
sys.exit(1 if config.get("setup_completed") is True else 0)'
}

launch_setupwizard() {
    python3 - <<'PY' &
import asyncio

from dbus_next.aio import MessageBus

BUS_NAME = "org.deletescapeos.Shell2"
OBJECT_PATH = "/org/deletescapeos/Shell2"
INTERFACE = "org.deletescapeos.Shell2"


async def main():
    last_error = None
    for _ in range(50):
        try:
            bus = await MessageBus().connect()
            introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
            obj = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
            iface = obj.get_interface(INTERFACE)
            if await iface.call_launch_app("setupwizard"):
                return
            last_error = RuntimeError("Shell2 refused to launch setupwizard")
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(0.1)

    raise SystemExit(f"Failed to launch setupwizard: {last_error}")


asyncio.run(main())
PY
    PIDS+=($!)
}

if [ "$1" = "mobile" ]; then
    python3 shell2.py --mobile &
    PIDS+=($!)

    if setup_needed; then
        launch_setupwizard
    else
        python3 labwc/mobile/status.py &
        PIDS+=($!)

        python3 labwc/mobile/home.py &
        PIDS+=($!)
    fi
else
    python3 shell2.py &
    PIDS+=($!)

    if setup_needed; then
        launch_setupwizard
    else
        python3 labwc/desktop/taskbar.py &
        PIDS+=($!)
    fi
fi

cleanup() {
    echo "Stopping processes..."
    kill "${PIDS[@]}" 2>/dev/null
    wait "${PIDS[@]}" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait "${PIDS[@]}"
