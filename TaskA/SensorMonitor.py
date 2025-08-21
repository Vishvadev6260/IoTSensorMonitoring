#!/usr/bin/env python3
import json, sqlite3, time, threading
from datetime import datetime
from sense_hat import SenseHat, ACTION_PRESSED

DB_PATH = "envirotrack.db"
CONFIG_PATH = "TaskA/enviro_config.json"

# Define colors for LED matrix
GREEN = (0, 255, 0)   # Comfortable/Aligned
RED   = (255, 0, 0)   # High
BLUE  = (0, 0, 255)   # Low
AMBER = (255, 191, 0) # Tilted
WHITE = (255, 255, 255)

class ConfigError(Exception):
    pass

class SensorMonitor:
    def __init__(self, config_path=CONFIG_PATH, db_path=DB_PATH):
        self.sense = SenseHat()
        self.sense.low_light = False

        self.config = self._load_and_validate_config(config_path)
        meta = self.config.get("meta", {})
        self.temp_offset   = float(meta.get("temperature_calibration_offset", -1.5))
        self.poll_seconds  = int(meta.get("poll_seconds", 10))
        self.rotate_seconds= int(meta.get("rotate_seconds", 5))

        self.paused = False
        self._latest = None            # latest numeric readings
        self._latest_classes = None    # latest class labels

        # DB connection
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

        # Joystick listener (non-blocking)
        self.sense.stick.direction_middle = self._on_middle_pressed

        # Display thread for LED rotation
        self._stop = threading.Event()
        self._display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self._display_thread.start()

    # ---------- Configuration & DB ----------
    def _load_and_validate_config(self, path):
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            raise ConfigError(f"Cannot read config '{path}': {e}")

        # Validate configuration
        for key in ("temperature", "humidity", "pressure", "orientation"):
            if key not in cfg:
                raise ConfigError(f"Missing '{key}' section in config.")

        def check_env_range(name):
            if name not in cfg or not all(k in cfg[name] for k in ("min", "max")):
                raise ConfigError(f"'{name}' must have min and max.")
            lo, hi = cfg[name]["min"], cfg[name]["max"]
            if not isinstance(lo, (int,float)) or not isinstance(hi, (int,float)) or lo >= hi:
                raise ConfigError(f"Invalid range for '{name}': min < max required.")

        for k in ("temperature", "humidity", "pressure"):
            check_env_range(k)

        # Check orientation range
        if "orientation" not in cfg or not all(a in cfg["orientation"] for a in ("pitch","roll","yaw")):
            raise ConfigError("Orientation must include pitch/roll/yaw with min/max.")
        for axis in ("pitch","roll","yaw"):
            ax = cfg["orientation"][axis]
            if not all(k in ax for k in ("min","max")) or ax["min"] >= ax["max"]:
                raise ConfigError(f"Invalid orientation range for {axis}.")

        cfg.setdefault("meta", {})
        return cfg

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL,
                humidity REAL,
                pressure REAL,
                pitch REAL,
                roll REAL,
                yaw REAL,
                temperature_status TEXT,
                humidity_status TEXT,
                pressure_status TEXT,
                orientation_status TEXT,
                ts TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    # ---------- Joystick ----------
    def _on_middle_pressed(self, event):
        if event.action == ACTION_PRESSED:
            self.paused = not self.paused
            self.sense.show_message("PAUSE" if self.paused else "RUN", scroll_speed=0.06, text_colour=WHITE)

    # ---------- Sensors, Classify, Log ----------
    def _read_sensors(self):
        t = self.sense.get_temperature() + self.temp_offset
        h = self.sense.get_humidity()
        p = self.sense.get_pressure()
        o = self.sense.get_orientation()
        return {
            "temperature": round(t, 1),
            "humidity": round(h, 1),
            "pressure": round(p, 1),
            "pitch": round(o["pitch"], 1),
            "roll": round(o["roll"], 1),
            "yaw": round(o["yaw"], 1),
        }

    def _bucket(self, v, lo, hi):
        if v < lo:  return "Low"
        if v > hi:  return "High"
        return "Comfortable"

    def _classify(self, r):
        cfg = self.config
        temp_c = self._bucket(r["temperature"], cfg["temperature"]["min"], cfg["temperature"]["max"])
        hum_c  = self._bucket(r["humidity"],    cfg["humidity"]["min"],    cfg["humidity"]["max"])
        prs_c  = self._bucket(r["pressure"],    cfg["pressure"]["min"],    cfg["pressure"]["max"])
        aligned = (
            cfg["orientation"]["pitch"]["min"] <= r["pitch"] <= cfg["orientation"]["pitch"]["max"] and
            cfg["orientation"]["roll"]["min"]  <= r["roll"]  <= cfg["orientation"]["roll"]["max"]  and
            cfg["orientation"]["yaw"]["min"]   <= r["yaw"]   <= cfg["orientation"]["yaw"]["max"]
        )
        ori_c = "Aligned" if aligned else "Tilted"
        return {"temperature": temp_c, "humidity": hum_c, "pressure": prs_c, "orientation": ori_c}

    def _log(self, r, c):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_logs
            (temperature, humidity, pressure, pitch, roll, yaw,
             temperature_status, humidity_status, pressure_status, orientation_status, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["temperature"], r["humidity"], r["pressure"], r["pitch"], r["roll"], r["yaw"],
            c["temperature"], c["humidity"], c["pressure"], c["orientation"],
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        ))
        self.conn.commit()

    # ---------- LED Display ----------
    def _color_for(self, key, label):
        if key == "orientation":
            return GREEN if label == "Aligned" else AMBER
        if label == "Comfortable": return GREEN
        if label == "High":        return RED
        if label == "Low":         return BLUE
        return WHITE

    def _display_loop(self):
        modes = ["temperature", "humidity", "pressure", "orientation"]
        idx = 0
        while not self._stop.is_set():
            if self._latest and self._latest_classes and not self.paused:
                key = modes[idx % len(modes)]
                c = self._latest_classes[key]
                col = self._color_for(key, c)
                r = self._latest

                if key == "temperature":
                    msg = f"T:{r['temperature']:.1f}"
                elif key == "humidity":
                    msg = f"H:{r['humidity']:.1f}"
                elif key == "pressure":
                    msg = f"P:{r['pressure']:.0f}"
                else:
                    msg = f"P:{r['pitch']:.0f}/R:{r['roll']:.0f}/Y:{r['yaw']:.0f}"

                self.sense.show_message(msg, scroll_speed=0.06, text_colour=col)

                idx += 1
            # rotate every rotate_seconds
            time.sleep(max(0.2, self.rotate_seconds * 0.2))

    # ---------- Main loop ----------
    def run(self):
        try:
            while not self._stop.is_set():
                if not self.paused:
                    r = self._read_sensors()
                    c = self._classify(r)
                    self._latest, self._latest_classes = r, c
                    self._log(r, c)

                    # Debugging output to see the readings and classifications
                    print(f"Sensor readings: {r}")
                    print(f"Classifications: {c}")
                
                time.sleep(self.poll_seconds)
        finally:
            self.cleanup()

    def cleanup(self):
        self._stop.set()
        try:
            self.sense.clear()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

def main():
    try:
        monitor = SensorMonitor()
    except ConfigError as e:
        print(f"[CONFIG ERROR] {e}")
        sys.exit(2)
    except Exception as e:
        print(f"[STARTUP ERROR] {e}")
        sys.exit(1)

    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nExiting...")
        monitor.cleanup()

if __name__ == "__main__":
    main()
