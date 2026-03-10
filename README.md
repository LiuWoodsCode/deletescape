Deletescape is a project to write a Python based shell and userspace for applications, similar to iOS or Android. It uses Qt 6 (PySide6) to render the user interface, and applications are expected to be written in Python.

Some things to note:
* Deletescape is very early in development, tons of elements are subject to change. As some examples:
    * You currently cannot set a PIN
    * There are no permissions
    * There is currently no concept of an "app manager", app sandboxes, user installed apps, etc
* Most of this assumes Windows, support for Linux dev stations and postmarketOS is planned but not currently being worked on.

## Build rootfs

```bash
python builder/build_rootfs.py --device-tree deviceconfig.json
```

## Install deps on debian

```bash
apt install python3-piexif libpyside6-py3-6.8 python3-psutil python3-requests
```

## Debugging in VS Code

When debugging deletescape, make sure you start a debugging session in boot.py.