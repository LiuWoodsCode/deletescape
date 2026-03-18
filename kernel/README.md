# Sayori
The Sayori kernel is the main low-ish level interface to interact with the host OS, and allows for tasks to be outsourced to many different "services".

## Processes
Sayori manages a list of processes. Each process can be mapped to either a Python thread, or a host OS process.

## Services
Services are the main thing that Sayori does. Each service runs in it's own Python process. Each process is made to be seperate systemd services that get started before the system gets into a Wayland session and we start the shell.

# The "privileged service"
The privileged service is the only one of those services that runs as root, and is meant for privileged actions in host OS space (e.g changing the hostname).

# FAQ

## Why Systemd? Why not OpenRC/SysVinit/MonikaRC/DDRC/[insert other init system]?
At this point, it's expected that whatever linux is running on the device is using systemd. In recent years systemd has become very popular among distros, and also very controversial for *reasons*. 

## Can an app modify Sayori's files?
It depends on if (and how) broken your installation is.

In most cases the system files will only be modifiable by root using POSIX access controls. This applies to not just Sayori, but all system files, and is enforced on installation. 

However, in the case that this fails, you might have a situation where the user running deletescape is also allowed to modify the system files. This is not just a Sayori issue, as in such case the device cannot be trusted due to malformed ACLs.

## Where does the name come from?
Doki Doki Literature Club.

## Windows 10? macOS? Ubuntu 4.04?
* Windows 10 is not supported; see docs/windows.md for more info
* I do not have Mac hardware to test code on, it may or may not work on macOS.
* Ubuntu 4.04 was released over 22 years ago!! It can't even run Python 3000! What did you expect?

The minimum tested Python version is 3.13.