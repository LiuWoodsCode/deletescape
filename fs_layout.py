from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UserDataLayout:
    base_dir: Path

    @property
    def root(self) -> Path:
        return self.base_dir / "userdata"

    @property
    def user(self) -> Path:
        return self.root / "User"

    @property
    def user_dcim(self) -> Path:
        return self.user / "DCIM"
    
    @property
    def data(self) -> Path:
        return self.root / "Data"

    @property
    def data_application(self) -> Path:
        return self.data / "Application"

    @property
    def data_system(self) -> Path:
        return self.data / "System"

    @property
    def applications(self) -> Path:
        return self.root / "Applications"

    def app_data_dir(self, app_id: str) -> Path:
        return self.data_application / str(app_id)

    def ensure_directories(self) -> None:
        directories = [
            self.root,
            self.user,
            self.user_dcim,
            self.data,
            self.data_application,
            self.data_system,
            self.applications,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


def get_user_data_layout(base_dir: Path | None = None) -> UserDataLayout:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent
    return UserDataLayout(base_dir=Path(base_dir))


def _merge_dir_contents(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for child in src_dir.iterdir():
        dst_child = dst_dir / child.name
        if child.is_dir():
            _merge_dir_contents(child, dst_child)
            try:
                child.rmdir()
            except Exception:
                pass
        else:
            if dst_child.exists():
                continue
            dst_child.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(dst_child))


def _move_legacy_path(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        if not dst.exists():
            shutil.move(str(src), str(dst))
            return True
        if not dst.is_dir():
            return False
        _merge_dir_contents(src, dst)
        try:
            src.rmdir()
        except Exception:
            pass
        return True

    if dst.exists():
        return False

    shutil.move(str(src), str(dst))
    return True


def migrate_legacy_user_data(base_dir: Path | None = None) -> dict[str, int]:
    layout = get_user_data_layout(base_dir)
    layout.ensure_directories()

    legacy_map: list[tuple[Path, Path]] = [
        (layout.base_dir / "DCIM", layout.user_dcim)
    ]

    migrated = 0
    skipped = 0

    for src, dst in legacy_map:
        try:
            moved = _move_legacy_path(src, dst)
            if moved:
                migrated += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    return {"migrated": migrated, "skipped": skipped}
