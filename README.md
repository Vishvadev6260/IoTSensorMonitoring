# IoT Sensor Monitoring 

This repository contains an IoT sensor monitoring system based on the Raspberry Pi and Sense HAT.

## Task A
**Task A** involves monitoring environmental parameters (temperature, humidity, pressure) and device orientation (pitch, roll, yaw) with the Raspberry Pi Sense HAT.Data is logged into a local SQLite database and displayed on the Sense HAT's LED matrix.

### Features: 
The device tracks temperature, humidity, pressure and orientation measurements. 
Data classification happens by applying pre-defined threshold values. 
The LED matrix provides immediate feedback to the user. 
- Database logging of sensor readings and classifications.

## How to Run: 
- Clone this repository.
The project requires the installation of necessary dependencies which include 'sense-hat`,`sqlite3` among others. 
- Run `SensorMonitor.py' in **Task A**. 
