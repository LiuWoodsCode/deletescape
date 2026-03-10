This is basically a log of devices I try this on.

# moto g power (2021) (via Debian trixie proot, Termux on LineageOS 23.2)
## Enviorment details:
* CPU arch: aarch64 (ARM64)
* Distro: Debian 13 (trixie) running inside Termux on LineageOS 23.2 (Android 16)
* Windowing system: X11
    * X server: Termux:X11
* Desktop environment: Xfce
    * Window manager: Xfwm4
* PySide6 version: Qt 6.10.2 (installed with `pip install pyside6 --break-system-packages`)
## Experience log
* Did it boot: Yes
    * Install PySide6 from pip instead of apt as libpyside6 in Debian doesn't seem to work
        * This might be good for readme
    * You also need to install some xcb cursor package in order for Qt to render
### Issues
* There are no drivers that use termux-api
    * This causes data like the battery, wifi, cellular, etc to appear as if the device did not include them.
    * This affects all devices that run deletescape through Termux.
* QtWebEngine crashes the Python process
    * When trying to launch Project Crimew, the window closes and the console prints "Segmentation fault".
    * This is most likely caused by the proot interfering with the Chromium sandbox rather than an issue in deletescape or crimew.
    * Weirdly enough, this doesn't affect the preloading that boot.py performs