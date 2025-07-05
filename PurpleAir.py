import os
import requests
import time
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

# Configuration
API_KEY = os.getenv("PURPLEAIR_API_KEY")  # Must be set in your environment
SENSORS_FILE = "sensors.txt"
DATA_DIR = Path("data")
FIELDS = [
    "firmware_version",
    "humidity",
    "temperature",
    "pressure",
    "voc",
    "pm2.5_cf_1"
]
CSV_FIELDS = ["timestamp", "datetime"] + FIELDS

def read_sensor_ids(filepath):
    with open(filepath, "r") as file:
        return [line.strip() for line in file if line.strip().isdigit()]

def fetch_sensor_data(sensor_id):
    url = f"https://api.purpleair.com/v1/sensors/{sensor_id}/history"
    end_time = int(time.time())
    start_time = end_time - (6 * 60 * 60)  # 6 hours ago
    params = {
        "start_timestamp": start_time,
        "end_timestamp": end_time,
        "average": 0,  # average every 60 minutes
        "fields": ",".join(FIELDS)
    }
    headers = {
        "X-API-Key": API_KEY
    }

    response = requests.get(url, params=params, headers=headers)
    if response.ok:
        return response.json()
    else:
        print(f"Failed to fetch data for sensor {sensor_id}: {response.status_code}")
        return None

def read_existing_timestamps(csv_path):
    if not csv_path.exists():
        return set()
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        return set(row["timestamp"] for row in reader)

def write_sensor_data(sensor_id, data):
    if not data or "data" not in data or "fields" not in data:
        print(f"No valid data to write for sensor {sensor_id}")
        return

    csv_path = DATA_DIR / f"{sensor_id}.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_timestamps = read_existing_timestamps(csv_path)

    rows = []
    for row_values in data["data"]:
        row_dict = dict(zip(data["fields"], row_values))
        ts = row_dict.get("time_stamp")
        if not ts or str(ts) in existing_timestamps:
            continue
        
        # Convert to timezone-aware datetimes
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_mtn = dt_utc.astimezone(ZoneInfo("America/Denver"))

        row = {
            "timestamp": ts,
            "datetime": dt_mtn.isoformat(),
            **{field: row_dict.get(field) for field in FIELDS}
        }
        rows.append(row)

    if not rows:
        print(f"No new rows to write for sensor {sensor_id}.")
        return

    # Sort rows by timestamp before writing
    rows.sort(key=lambda row: int(row["timestamp"]))

    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} new rows to {csv_path}")

def main():
    if not API_KEY:
        raise EnvironmentError("PURPLEAIR_API_KEY environment variable not set.")
    
    sensor_ids = read_sensor_ids(SENSORS_FILE)
    print(f"Found {len(sensor_ids)} sensor(s). Fetching data...")

    for sensor_id in sensor_ids:
        print(f"\nFetching data for sensor {sensor_id}...")
        data = fetch_sensor_data(sensor_id)
        write_sensor_data(sensor_id, data)

if __name__ == "__main__":
    main()
