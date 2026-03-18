# Boot configuration cmdline

Options can be passed into boot.py to configure certain options about the session.

## --fullscreen
* Type: boolean (true if specified)
If specified, deletescape will render in full screen on the primary monitor, rather than inside a window.

## --recovery
* Type: boolean (true if specified)
If specified, deletescape's recovery mode will be triggered with reason code "RECOVERY_REQUESTED".

## --no-webengine-preload
* Type: boolean (true if specified)
If specified, the boot chain will not preload an instance of QtWebEngine. 

By default, the boot process attempts to preload QtWebEngine as it's slow to load and often causes the window to close/reopen. This can be used if QtWebEngine causes an instant crash on the device.

## --llvm
* Type: boolean (true if specified)
If specified, boot will attempt to tell Qt to render with software OpenGL. This isn't tested and you may be better off with automatic detection.

## --kiosk 
* Type: boolean (true if specified)
If specified, deletescape will launch in embedded mode. You must specify an app in userconfig.embed_appid for this to work.

This flag is expected to be true on embedded deletescape builds.