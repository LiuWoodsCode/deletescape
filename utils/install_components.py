import argparse
import os
import subprocess
import sys
from pathlib import Path


PACKAGES = ["PySide6", "markdown", "piexif", "requests", "psutil"]


def get_venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def create_venv(venv_path: Path) -> None:
    if venv_path.exists():
        print(f"Using existing virtual environment at: {venv_path}")
        return

    print(f"Creating virtual environment at: {venv_path}")
    run_command([sys.executable, "-m", "venv", str(venv_path)])


def install_packages(venv_python: Path) -> None:
    print("Installing required packages...")
    run_command([str(venv_python), "-m", "pip", "install", *PACKAGES])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a virtual environment and install required components."
    )
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Path to the virtual environment directory (default: .venv)",
    )
    args = parser.parse_args()

    venv_path = Path(args.venv).resolve()
    create_venv(venv_path)

    venv_python = get_venv_python(venv_path)
    if not venv_python.exists():
        print(f"Virtual environment Python not found: {venv_python}")
        return 1

    install_packages(venv_python)
    print("Setup complete.")
    print(f"Virtual environment: {venv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())