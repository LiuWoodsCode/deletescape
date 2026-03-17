# Add virtual keyboard support to QtWebEngine sites
* QtWebEngine currently 

# License viewer application
Provide a hidden application to view the same licenses as seen in the setup wizard, launched from the Settings app in some legal section

# Migration (backup and restore)
Add the ability to backup data from a non-embedded deletescapeOS device or a supported other platform and restore it on the device. 

## Some long stretches 
Migration things I may or may not go through with.

### Source -> Target app migration
When your source is running a non-deletescape OS, perhaps we could allow app devs to register the bundle IDs of their iOS, Android, etc apps so the device can install them from the app store.

### Move to deletescapeOS from iOS
libimobiledevice lets you take backups of iOS devices over USB. As all mobile devices shipping with the OS should have USB-C, it could be possible to plug in an iPhone and have it backup the contents and convert them into deletescapeOS's userdata structure. Considering that these are basically the same as iTunes backups, we could probably restore basically all of the data from an iPhone, including all of your settings.

### Move to deletescapeOS from Android
This is actually quite harder with just ADB, if not at all. Google has locked down the ability of desktop backups (adb backup) quite a lot over the past few years, so the only thing you might be able to do is move all of the media (/storage/emulated/0) that isn't in Google Photos, the preferences we can get with getprop and settings, and the list of installed apps.

# Notches, hole punches, Dynamic Island, oh my!
Currently, deletescape assumes that the user can see 100% of the screen, with no obstructions in the way. On many newer phones however, this does not apply. 

# Assistant integration with deletescape
Work on integrating the digital assistant with the operating system, for example launching applications.

# Embedded deletescape
Add necessary functionality for running deletescapeOS and applications written for it on embedded systems (think: digital signage, kiosks, etc).

This is currently being worked on in the "embedded_bringup" branch.

# Compliance with Online Safety Act, that one California bill, etc
In states that require age verification and/or age attestation, the OOBE should perform a check and block setup in these regions, only allowing you to shut down the device. The message should also tell you next steps.

Internally, this most likely would be a GeoIP check to check which country and/or state you are in, and if it's on the blacklist, throw an error. 
For example:
> To comply with the Online Safety Act, deletescapeOS cannot be used in the United Kingdom. If you purchased this device, please return it to the retailer for a refund.

Also, if you click a button like "why" or "learn more", the system should tell you why we can't comply with the bill/law (as OSS software) and what to do if you recieved this message in error

For example:
> The Online Safety Act requires us to use "reasonable measures" (like a government ID or AI face scan) to detect your age and block access to certain features for users under 18. This is impossible for me as an open source developer to comply with, as it would require including nonfree code with the program, and would potentially violate your privacy. 

# Captive portal / WAN check
Currently if a network has a captive portal, besides opening the internet browser, you have no idea that your internet is currently being held captive, or if you even have internet at all! (Damm you iOS 26 Personal Hotspot!)

This is easy and hard to implement at the same time. The setup is basically:
* Get response from a connection test server
    * This can be from Google, Apple, Mozilla, GNOME, etc...
    * Even example.com works well (though ICANN doesn't recommend it for this use)
* Check the response we got:
    * If it's expected, do nothing
    * Else:
        * If on the home screen, automatically launch the hidden captive portal handler app (escaptive)
        * If in another app, use a notification to prompt the user to launch escaptive

# Low power / eco mode
* Attempts to save battery life by telling the system to do less
    * Slow down background task ticks
    * Update the status bar updates way less (every 15 sec for time, every 45 sec for everything else)

# Battery health warnings
If it appears that your battery health is very low, we should probably tell you in a notification. The abstraction layer for batteries already supports battery health reporting, and settings has code for showing warnings below a certain health.

# Less on budget, more on flagship
In the device tree, it could be possible to list the performance class of a device. This performance class will control if certain effects will be used, among other things. 

For example, a low power smartwatch or old budget model probably shouldn't be able to assign itself a 1ms tick background task, nor should we try using GPU intensive effects.

Meanwhile, a Pixel 10 should be allowed to use all of the visual flare we can throw at it (as long as the Tensor GPU is supported.)

# Termux support
* Disable QtWebEngine sandbox 
    * Chromium's sandbox HATES being inside a proot
    * Attempting to launch Chromium with the sandbox inside a proot will cause a segfault
* Drivers for termux
    * Use termux-api to interface with some Android APIs

# Handle Deletescape itself crashing
* "Deletescape itself" here refers to anything that is not an app
* For drivers:
    * Show a notification alerting of the issue every time after you unlock
    * Something like iOS's part warnings, though not for parts pairing mismatches

# Native apps
* Allow creation of native applications
    * Registered the same as normal apps except they do not get Qt access
    * In fact, the entire shell is hidden except for new overlays
    * This allows apps not following the LGPL/GPL to be made for deletescape
* Overlay version of status bar and software home
* On devices with hw home, make sure we receive that event globally
* Expose a big chunk of the Deletescape API's through IPC, however:
    * Background tasks can only be written in Python

# Removable media support
* Notifications are displayed when a SD card or USB drive is connected
* You can manage it in Files so long as the kernel can mount it

# User installable apps
* Apps can be packaged into .pkg files
    * PKGs are just renamed ZIP files of the contents of its app directory, don't confuse this with Apple's format for installing macOS apps
* App installer
    * App that handles the installation of PKGs

# Use the Settings UI styling for all apps (DeletescapeUI)
* The Settings UI was pulled from the now-cancled SVMobile (Sun Valley Mobile) project
* It aligns nicely with Fluent Design with elements from Windows 10 Mobile (MDL2)

# URL scheme handling (deep linking?)
* Apps could register protocol handlers
* Both links and QtWebEngine supports app's protocols

# Privileged service
* Similar to Android, plenty of actions should only be able to be performed by the system, and can't be put in the main API as they need root, or at least a higher level than the main user
* The privileged service bridges the gap:
    * This service runs as root or a higher permission level
    * Only needed actions can be done with it
    * Only some apps with some permissions can do some things
        * A user installed game with basically no permissions shouldn't be asking to turn on the Bluetooth

# Over the Air (OTA) updates
* In the background, updates can be downloaded over Wi-Fi (or cellular if user wants)
* You can check for updates in settings
    * Each update contains data like the displayed name, changelog, banner image, estimated time of install, size of update package compacted, size of contents extracted, etc
* Once downloaded:
    * The user can manually install the update in settings
    * The device can automatically update if user wants
* Installation:
    * The device closes the Deletescape shell and runs UpdateShell
    * In UpdateShell:
        * US checks the update files for corruption
            * A copy of the directory structure 
            * If failed, reboot back into the Deletescape shell
        * US copies the existing shell as a backup
        * US copies new shell files over the existing shell
            * If failed, restore from the backup and reboot back into the Deletescape shell
        * US then performs migration tasks (if needed)
        * US quits and boots the new shell

# UpdateShell
UpdateShell is a program that handles system updates and certain other situations where we cannot have the main deletescape running.

The following scenerios would use UpdateShell:
* System updates
* Factory reset
* Preparing for first boot

 
# Factory reset
An option could be added to settings to "Erase user data". Initating a factory reset would require you to confirm mutiple times that you intend to reset the device. A factory reset simply deletes userdata/ and config.json and restores the contents of defaults/

# Deletescape SSH server
An SSH server could be provided by the OS using paramiko to allow a special shell specific to deletescape to be accessed. This shell would have the following features:
* Get device info
* Open apps
* Install apps
* Access the filesystem
* Enter recovery mode
* Access a bash shell
* And plenty more

This is being worked on in "kangel_dev" branch.

# Deletescape DFU protocol
* Accessible in recovery mode
* Allows you to:
    * Get information, like:
        * Reason for entering recovery
        * Device info
        * OS, kernel, py, firmware info
    * Dump logs
    * Factory reset
    * Flash new deletescape rootfs

A lot of this can be done by KAngel as of right now.

# Make a lot of the UIs seperate windows
* Each app now runs in a seperate python and manages their own QApplication
* A test implementation is avaliable in ../v2
* Apps and services communicate over IPC (?)
* This would allow features like:
    * Better OOM management
    * RAM savings (we kill what we don't need)
    * Daemons (remember those services?)
    * etc

# Psuedokernel
A new "kernel" could be developed that's running inside Python, handling scheduling, devices, resources, etc.

# Authentication
* Probably just pin unlock for right now

# More abstraction layers
* WiFi (Completed)
* Bluetooth
* Location (Completed)
* Sensors

# Permission system

# More testing on non-Windows hardware
* This is because most of our target phones don't run Windows
* Test targets:
    * Linux machine (Debian amd64)
        * This might be possible with Crostini on my CrOS Flex laptop
    * Nexus 5 (pmOS armv7)
        * Does Qt even support armv7 anymore?

# File structure change (previously medium term)
* Use a specifc directory for all user data
    * User data is split into a few:
        * User - Files made or downloaded by the user go here (e.g pictures, music, downloads, etc). Equivalent to /home on Linux, On My iPhone on iOS, or most of /storage/emulated/0 on Android
        * Data - Contains subfolders
            * Application - Data for applications (e.g config files, cache). Equivalent to local AppData on Windows.
            * System - Data that is created and used by Deletescape and its services (e.g SMS logs, call history, etc)
        * Applications - User installed applications. User version of ./apps
* With this, we can also restructure the FS layout to be more organized
* For example:
    * ./DCIM/jvne.png -> ~/userdata/User/DCIM/jvne.png
    * ~/Downloads/maia-arson-crimew-research.docx -> ~/userdata/User/Downloads/maia-arson-crimew-research.docx
    * ./userdata/msghist.json -> ~/userdata/Data/System/Telephony/Messages/history.json
    * ./userdata/weather.json -> ~/userdata/Data/Application/weather/config.json

# File manager (previously short term)
* Manage files on the storage of the device
    * Specifically, the User part

# Out of box experience (previously long term)
* New hidden app: setupwizard
    * Handles most of the OOBE (UI, backend, etc)
* OOBE is triggered if setup_completed is false in config.json
    * Once completed, that value is made true
* When setup_complete is false, home opens up setupwizard rather than home
* Mockup means that the step should only have UI, but no real backend code and no saving the entered data
* Setup steps:
    * Internal Beta notice
    * Language and region (mockup, while the usual English is there, there ares several fictional languages listed alongside, and the only countries are United States, Canada, Inkopolis, and Colony 9)
    * Network connectivity (mockup)
    * License agreement (mockup)
    * Time format
    * Light/Dark mode
    * "Welcome to Deletescape" (exit)

# Design new icons
* We designed the new icons (everything except bgtest and notifytest), but forgot to include them in the build sent to my USB drive... *sigh*
    * You will need to apply them manually
* Right now most of the apps are using icons from iOS 6
* And some are from Windows 11's apps
* And some are placeholders
* This is fine for prototyping but doesn't fit Fluent Design
