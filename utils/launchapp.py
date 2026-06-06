#!/usr/bin/env python3

import asyncio
from dbus_next.aio import MessageBus

BUS_NAME = "org.deletescapeos.Shell2"
OBJECT_PATH = "/org/deletescapeos/Shell2"
INTERFACE = "org.deletescapeos.Shell2"


async def main():
    app_id = input("App ID: ").strip()

    bus = await MessageBus().connect()

    introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
    obj = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
    iface = obj.get_interface(INTERFACE)

    result = await iface.call_launch_app(app_id)

    if result:
        print(f"Launched: {app_id}")
    else:
        print(f"Failed to launch: {app_id}")


if __name__ == "__main__":
    asyncio.run(main())