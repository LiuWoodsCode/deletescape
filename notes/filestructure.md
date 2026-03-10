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
