import getpass
import hashlib
from pathlib import Path


def generate_pin_from_key(path: Path) -> str:
    try:
        data = path.read_bytes()
    except Exception as e:
        print(f"error reading key file: {e}")
        return None

    digest = hashlib.sha256(data).hexdigest()
    pin_int = int(digest, 16) % 1_000_000
    return f"{pin_int:06d}"


def main():
    username = getpass.getuser()
    key_path = Path("userdata/Data/System/KAngel/kangel_host_key.pem")

    pin = generate_pin_from_key(key_path)

    if pin is None:
        print("failed to generate pin")
        return

    print("=== login credentials ===")
    print(f"username: {username}")
    print(f"pin:      {pin}")


if __name__ == "__main__":
    main()