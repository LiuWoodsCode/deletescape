import json
from multiprocessing.connection import Listener
from endpoints import endpoint, dispatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
import subprocess
import platform
import os
import platform
import socket
import sys
CONFIG_FILE_NAME = "config.json"
DEVICE_CONFIG_FILE_NAME = "deviceconfig.json"
OS_BUILD_CONFIG_FILE_NAME = "osconfig.json"

# ---------------------------
# SYSTEM SYSCALL SURFACE
# ---------------------------
@dataclass
class OSBuildConfig:
    os_name: str = "Deletescape"
    os_version: str = "0.1.0"
    build_number: int = 1
    build_id: str = ""
    channel: str = "dev"
    builder_username: str = ""
    builder_hostname: str = ""
    build_datetime: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OSBuildConfig":
        os_name = data.get("os_name", "Deletescape")
        os_version = data.get("os_version", "0.1.0")
        build_number = data.get("build_number", 1)
        build_id = data.get("build_id", "")
        channel = data.get("channel", "dev")
        builder_username = data.get("builder_username", "")
        builder_hostname = data.get("builder_hostname", "")
        build_datetime = data.get("build_datetime", "")

        return cls(
            os_name=os_name if isinstance(os_name, str) else str(os_name),
            os_version=os_version if isinstance(os_version, str) else str(os_version),
            build_number=int(build_number) if isinstance(build_number, (int, float, str)) else 1,
            build_id=build_id if isinstance(build_id, str) else str(build_id),
            channel=channel if isinstance(channel, str) else str(channel),
            builder_username=builder_username if isinstance(builder_username, str) else str(builder_username),
            builder_hostname=builder_hostname if isinstance(builder_hostname, str) else str(builder_hostname),
            build_datetime=build_datetime if isinstance(build_datetime, str) else str(build_datetime),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "build_number": self.build_number,
            "build_id": self.build_id,
            "channel": self.channel,
            "builder_username": self.builder_username,
            "builder_hostname": self.builder_hostname,
            "build_datetime": self.build_datetime,
        }


class OSBuildConfigStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.path = self.base_dir / OS_BUILD_CONFIG_FILE_NAME

    def load(self) -> OSBuildConfig:
        if not self.path.exists():
            return OSBuildConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return OSBuildConfig.from_dict(data)
        except Exception:
            pass
        return OSBuildConfig()

    def save(self, config: OSBuildConfig) -> None:
        self.path.write_text(
            json.dumps(config.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        
@endpoint("kernel.kinfo")
def uname():
    u = os.uname()

    return {
        "sysname":  "Sayori",
        "nodename": socket.gethostname(),
        "release":  "alpha",
        "version":  "0",
        "machine":  u.machine
    }

@endpoint("kernel.pid")
def pid():
    return os.getpid()


@endpoint("ping")
def ping():
    return "pong"


# ---------------------------
# SERVICE LOOP
# ---------------------------

def run():
    listener = Listener(("localhost", 9150), authkey=b"secret")

    print("Kernel info service online")

    while True:
        conn = listener.accept()

        try:
            msg = conn.recv()
            conn.send(dispatch(msg))
        finally:
            conn.close()


if __name__ == "__main__":
    run()