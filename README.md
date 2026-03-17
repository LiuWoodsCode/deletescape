Deletescape is a project to write a Python based shell and userspace for applications, similar to iOS or Android. It uses Qt 6 (PySide6) to render the user interface, and applications are expected to be written in Python.

`deletescapeOS` is currently the working name of the system, however this is not a final name. Sometime before 1.0 a new name will need to be decided. 

Some things to note:
* Deletescape is very early in development, tons of elements are subject to change. As some examples:
    * You currently cannot set a PIN
    * There are no permissions
* Most of this assumes Windows, support for Linux dev stations and postmarketOS is currently being worked on.

## Build rootfs

```bash
python builder/build_rootfs.py --device-tree deviceconfig.json
```

## Debugging in VS Code

When debugging deletescape, make sure you start a debugging session in boot.py.