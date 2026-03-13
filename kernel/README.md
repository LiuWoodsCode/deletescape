# Sayori
The Sayori kernel is the main low-ish level interface to interact with the host OS, and allows for tasks to be outsourced to many different "services".

## Processes
Sayori manages a list of 

## Services
Services are the main thing that Sayori does. Each service runs in it's own Python process. Each process is made to be seperate systemd services that get started before the system gets into a Wayland session and we start the shell.

# The "privileged service"
The privileged service is the only service that runs as root  