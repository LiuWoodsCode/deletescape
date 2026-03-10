# Support for Termux
Termux is a supported target for running deletescape on many Android devices, and is the reccomended way to try out the operating system if your device doesn't support postmarketOS. However, even though most of Termux:API is standard across Android devices, there is an exception; sensors.

## Sensor drivers
While the majority of termux-api's output's will output in the same way across devices, the sensors are an exception. Each device has it's own sensors which we need to convert to the standardized types which sensors.py accepts.

Drivers for the termux-sensor implementation of the sensor driver should be separate from any implementation for pmOS. 

For example:
* For borneo (moto g power 2021):
    * `drivers/sensors/borneo_pmos.py` - driver for borneo in pmOS
    * `drivers/sensors/borneo_termux.py` - driver for borneo using termux-sensors
