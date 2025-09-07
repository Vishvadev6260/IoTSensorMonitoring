import time
import sqlite3
import json
import os
from sense_hat import SenseHat

# Initialize the Sense HAT
sense = SenseHat()

# Load config file
with open("enviro_config.json") as f:
    config = json.load(f)

# Get the min and max values from the config file
min_temp = config['temperature']['min']
max_temp = config['temperature']['max']
min_humidity = config['humidity']['min']
max_humidity = config['humidity']['max']
min_pressure = config['pressure']['min']
max_pressure = config['pressure']['max']
orientation_ranges = config['orientation']

# Database setup
db_path = 'envirotrack.db'
if not os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE sensor_data (
            timestamp TEXT,
            temperature REAL,
            humidity REAL,
            pressure REAL,
            orientation_status TEXT,
            pitch REAL,
            roll REAL,
            yaw REAL
        )
    ''')
    conn.commit()
    conn.close()

# Function to classify the temperature
def classify_temperature(temp):
    if temp < min_temp:
        return "Low"
    elif min_temp <= temp <= max_temp:
        return "Comfortable"
    else:
        return "High"

# Function to classify humidity
def classify_humidity(humidity):
    if humidity < min_humidity:
        return "Low"
    elif min_humidity <= humidity <= max_humidity:
        return "Comfortable"
    else:
        return "High"

# Function to classify pressure
def classify_pressure(pressure):
    if pressure < min_pressure:
        return "Low"
    elif min_pressure <= pressure <= max_pressure:
        return "Comfortable"
    else:
        return "High"

# Function to classify orientation
def classify_orientation(pitch, roll, yaw):
    if abs(pitch) > orientation_ranges['pitch'] or abs(roll) > orientation_ranges['roll'] or abs(yaw) > orientation_ranges['yaw']:
        return "Tilted"
    return "Aligned"

# Function to display the status on the LED matrix
def display_status(temp_class, humidity_class, pressure_class, orientation_class):
    colors = {
        "Low": (255, 0, 0),       # Red
        "Comfortable": (0, 255, 0), # Green
        "High": (0, 0, 255),      # Blue
        "Tilted": (255, 165, 0),  # Amber
        "Aligned": (0, 255, 255)  # Cyan
    }
    
    sense.show_message(f"Temp: {temp_class}, Humidity: {humidity_class}", text_colour=colors[temp_class])
    sense.show_message(f"Pressure: {pressure_class}, Orientation: {orientation_class}", text_colour=colors[orientation_class])

# Main loop to read sensor data
while True:
    # Read the sensors
    temp = sense.get_temperature()
    humidity = sense.get_humidity()
    pressure = sense.get_pressure()
    
    pitch, roll, yaw = sense.get_orientation_degrees().values()

    # Classify sensor readings
    temp_class = classify_temperature(temp)
    humidity_class = classify_humidity(humidity)
    pressure_class = classify_pressure(pressure)
    orientation_class = classify_orientation(pitch, roll, yaw)

    # Log data to SQLite database
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''
        INSERT INTO sensor_data (timestamp, temperature, humidity, pressure, orientation_status, pitch, roll, yaw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, temp, humidity, pressure, orientation_class, pitch, roll, yaw))
    conn.commit()
    conn.close()

    # Display on the LED matrix
    display_status(temp_class, humidity_class, pressure_class, orientation_class)

    time.sleep(10)  # Wait 10 seconds before next reading
