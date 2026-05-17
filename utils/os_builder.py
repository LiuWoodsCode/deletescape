#!/usr/bin/env python3

"""
mobileos_builder.py

Builds a bootable Debian-based QEMU disk image using debootstrap.

Features:
- Creates raw disk image
- Partitions + formats image
- Installs Debian with debootstrap
- Installs:
    - PySide6
    - markdown
    - piexif
    - requests
    - psutil
- Creates user: ironmouse
- Installs lightweight X session
- Enables autologin into X
- Installs QEMU guest basics
- Boots with QEMU

REQUIREMENTS:
    sudo apt install \
        debootstrap \
        qemu-system-x86 \
        qemu-utils \
        parted \
        dosfstools \
        e2fsprogs \
        systemd-container

Run as root:
    sudo python3 mobileos_builder.py
"""

import os
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path

# =========================
# CONFIG
# =========================

IMAGE_NAME = "ironmouse_os.img"
IMAGE_SIZE = "8G"
EFI_IMAGE_SIZE = "256M"
OVMF_CODE_PATH = "/usr/share/OVMF/OVMF_CODE.fd"
OVMF_VARS_PATH = "/usr/share/OVMF/OVMF_VARS.fd"

MOUNT_DIR = "/tmp/deletescape_buildroot"

HOSTNAME = "emulator"
USERNAME = "ironmouse"
PASSWORD = "123456"

DEBIAN_RELEASE = "trixie"
MIRROR = "http://deb.debian.org/debian"

ARCH = "amd64"
BOOT_TYPE = "bios"

EFI_PARTITION_MOUNT = "/boot/efi"

# =========================
# HELPERS
# =========================

def run(cmd, check=True):
    print(f"\n[RUN] {' '.join(cmd)}\n")
    subprocess.run(cmd, check=check)

def sh(cmd, check=True):
    print(f"\n[SHELL] {cmd}\n")
    subprocess.run(cmd, shell=True, check=check)

def write(path, content):
    print(f"[WRITE] {path}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def parse_args():
    parser = argparse.ArgumentParser(description="Build a Debian-based QEMU disk image")
    parser.add_argument(
        "--boot-type",
        choices=("bios", "uefi"),
        default=BOOT_TYPE,
        help="Select the firmware boot type for the generated image",
    )
    return parser.parse_args()

# =========================
# CLEANUP
# =========================

def cleanup():
    try:
        sh(f"umount -lf {MOUNT_DIR}/dev/pts", check=False)
        sh(f"umount -lf {MOUNT_DIR}/dev", check=False)
        sh(f"umount -lf {MOUNT_DIR}/proc", check=False)
        sh(f"umount -lf {MOUNT_DIR}/sys", check=False)
        sh(f"umount -lf {MOUNT_DIR}", check=False)
    except:
        pass

# =========================
# MAIN
# =========================

def main(boot_type):
    cleanup()

    os.makedirs(MOUNT_DIR, exist_ok=True)

    # =====================================
    # Create image
    # =====================================

    run([
        "qemu-img",
        "create",
        "-f",
        "raw",
        IMAGE_NAME,
        IMAGE_SIZE
    ])

    # =====================================
    # Partition image
    # =====================================

    if boot_type == "uefi":
        sh(f"parted -s {IMAGE_NAME} mklabel gpt")
        sh(f"parted -s {IMAGE_NAME} mkpart ESP fat32 1MiB {EFI_IMAGE_SIZE}")
        sh(f"parted -s {IMAGE_NAME} set 1 esp on")
        sh(f"parted -s {IMAGE_NAME} mkpart primary ext4 {EFI_IMAGE_SIZE} 100%")
    else:
        sh(f"parted -s {IMAGE_NAME} mklabel msdos")
        sh(f"parted -s {IMAGE_NAME} mkpart primary ext4 1MiB 100%")
        sh(f"parted -s {IMAGE_NAME} set 1 boot on")

    # =====================================
    # Attach loop device
    # =====================================

    LOOP = subprocess.check_output(
        ["losetup", "--find", "--partscan", "--show", IMAGE_NAME],
        text=True
    ).strip()

    PART = LOOP + "p1"
    EFI_PART = LOOP + "p2"

    print(f"[LOOP DEVICE] {LOOP}")

    # =====================================
    # Format partition
    # =====================================

    if boot_type == "uefi":
        run(["mkfs.vfat", "-F", "32", EFI_PART])
        run(["mkfs.ext4", "-F", PART])
    else:
        run(["mkfs.ext4", "-F", PART])

    # =====================================
    # Mount filesystem
    # =====================================

    if boot_type == "uefi":
        run(["mount", PART, MOUNT_DIR])
        run(["mkdir", "-p", f"{MOUNT_DIR}{EFI_PARTITION_MOUNT}"])
        run(["mount", EFI_PART, f"{MOUNT_DIR}{EFI_PARTITION_MOUNT}"])
    else:
        run(["mount", PART, MOUNT_DIR])

    # =====================================
    # Bootstrap Debian
    # =====================================

    run([
        "debootstrap",
        "--arch", ARCH,
        DEBIAN_RELEASE,
        MOUNT_DIR,
        MIRROR
    ])

    # =====================================
    # Mount virtual FS
    # =====================================

    run(["mount", "--bind", "/dev", f"{MOUNT_DIR}/dev"])
    run(["mount", "--bind", "/dev/pts", f"{MOUNT_DIR}/dev/pts"])
    run(["mount", "-t", "proc", "proc", f"{MOUNT_DIR}/proc"])
    run(["mount", "-t", "sysfs", "sys", f"{MOUNT_DIR}/sys"])

    # =====================================
    # APT sources
    # =====================================

    write(
        f"{MOUNT_DIR}/etc/apt/sources.list",
        f"""
deb {MIRROR} {DEBIAN_RELEASE} main contrib non-free-firmware
"""
    )

    # =====================================
    # Hostname
    # =====================================

    write(
        f"{MOUNT_DIR}/etc/hostname",
        HOSTNAME + "\n"
    )

    # =====================================
    # fstab
    # =====================================

    if boot_type == "uefi":
        write(
            f"{MOUNT_DIR}/etc/fstab",
            """
/dev/sda2 / ext4 defaults 0 1
/dev/sda1 /boot/efi vfat umask=0077 0 1
"""
        )
    else:
        write(
            f"{MOUNT_DIR}/etc/fstab",
            """
/dev/sda1 / ext4 defaults 0 1
"""
        )

    # =====================================
    # Chroot setup script
    # =====================================

    setup_script = f'''
#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive
export TARGET_DISK="{LOOP}"
export BOOT_TYPE="{boot_type}"

apt update

apt purge -y \
    ifupdown \
    ifupdown2 \
    isc-dhcp-client \
    resolvconf || true

apt install -y \
    linux-image-amd64 \
    systemd-sysv \
    sudo \
    network-manager \
    net-tools \
    xorg \
    xinit \
    openbox \
    xterm \
    x11-apps \
    lightdm \
    lightdm-gtk-greeter \
    python3 \
    python3-pyside6* \
    python3-markdown \
    python3-piexif \
    python3-requests \
    python3-psutil \
    mesa-utils \
    pulseaudio \
    dbus-x11 \
    openssh-server

if [ "$BOOT_TYPE" = "uefi" ]; then
    apt install -y grub-efi-amd64
else
    apt install -y grub-pc
fi

echo "root:root" | chpasswd

useradd -m -s /bin/bash ironmouse
echo "ironmouse:ironmouse" | chpasswd

usermod -aG sudo ironmouse

mkdir -p /home/ironmouse/.config/openbox

if [ "$BOOT_TYPE" = "uefi" ]; then
    mkdir -p /boot/efi
fi

cat > /home/ironmouse/.config/openbox/autostart << EOF
xeyes &
EOF

cat > /etc/lightdm/lightdm.conf << EOF
[Seat:*]
autologin-user=ironmouse
autologin-user-timeout=0
user-session=openbox
EOF

chown -R ironmouse:ironmouse /home/ironmouse

if [ "$BOOT_TYPE" = "uefi" ]; then
    grub-install \
        --target=x86_64-efi \
        --efi-directory=/boot/efi \
        --bootloader-id=deletescape \
        --removable
fi

if [ "$BOOT_TYPE" = "bios" ]; then
    grub-install "$TARGET_DISK"
fi

update-grub

systemctl enable NetworkManager
systemctl enable ssh
systemctl enable lightdm
'''

    write(f"{MOUNT_DIR}/root/setup.sh", setup_script)

    run(["chmod", "+x", f"{MOUNT_DIR}/root/setup.sh"])

    # =====================================
    # Run setup inside chroot
    # =====================================

    run(["chroot", MOUNT_DIR, "/root/setup.sh"])

    # =====================================
    # Cleanup inside image
    # =====================================

    sh(f"rm -f {MOUNT_DIR}/root/setup.sh")

    # =====================================
    # Unmount everything
    # =====================================

    cleanup()

    run(["losetup", "-d", LOOP])

    print("\n=====================================")
    print("IMAGE BUILD COMPLETE")
    print("=====================================\n")

    print("Boot with:\n")

    if boot_type == "uefi":
        print(f"""
qemu-system-x86_64 \\
    -m 4096 \\
    -smp 4 \\
    -drive file={IMAGE_NAME},format=raw \\
    -drive if=pflash,format=raw,readonly=on,file={OVMF_CODE_PATH} \\
    -drive if=pflash,format=raw,file={OVMF_VARS_PATH} \\
    -boot c \\
    -enable-kvm \\
    -vga virtio
""")
    else:
        print(f"""
qemu-system-x86_64 \\
    -m 4096 \\
    -smp 4 \\
    -drive file={IMAGE_NAME},format=raw \\
    -boot c \\
    -enable-kvm \\
    -vga virtio
""")

if __name__ == "__main__":
    try:
        args = parse_args()
        main(args.boot_type)
    finally:
        cleanup()