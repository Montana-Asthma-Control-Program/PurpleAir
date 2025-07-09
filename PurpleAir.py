import os
import requests
import time
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

# Configuration
API_KEY = os.getenv("PURPLEAIR_API_KEY")  # Must be set in your environment
SENSORS_FILE = "sensors.csv"
DATA_DIR = Path("data")
CSV_FIELDS = ["timestamp", "datetime", 
              "Raw PM2.5 (µg/m³)", "Relative Humidity (%)", 
              "Raw PM2.5 (US EPA) (µg/m³)", "US EPA PM2.5 (US EPA) (AQI)"]


def apply_epa_pm_correction(x, rh):
    """
    Applies a stepwise correction to PM2.5 values using RH and PM2.5 breakpoints.
    

    Parameters:
        x (float): Raw PM2.5 (cf_atm)
        rh (float): Relative humidity (%)

    Returns:
        float: Corrected PM2.5
    """
    if x < 0 or x is None or rh is None:
        return None

    if 0 <= x < 30:
        return 0.524 * x - 0.0862 * rh + 5.75

    elif 30 <= x < 50:
        w = x / 20 - 1.5
        return (0.786 * w + 0.524 * (1 - w)) * x - 0.0862 * rh + 5.75

    elif 50 <= x < 210:
        return 0.786 * x - 0.0862 * rh + 5.75

    elif 210 <= x < 260:
        w = x / 50 - 4.2  # equivalent to x/50 - 21/5
        term1 = (0.69 * w + 0.786 * (1 - w)) * x
        term2 = -0.0862 * rh * (1 - w)
        term3 = 2.966 * w
        term4 = 5.75 * (1 - w)
        term5 = 8.84e-4 * x**2 * w
        return term1 + term2 + term3 + term4 + term5

    elif x >= 260:
        return 2.966 + 0.69 * x + 8.84e-4 * x**2

    return None  # catch-all fallback

def calc_aqi(Cp, Ih, Il, BPh, BPl):
    """
    Calculate the AQI given concentration and breakpoint values.
    """
    a = Ih - Il
    b = BPh - BPl
    c = Cp - BPl
    return round((a / b) * c + Il)


def aqi_from_pm(pm):
    """
    Convert PM2.5 concentration to AQI using EPA standards.
    """
    if pm is None or isinstance(pm, str):
        return "-"
    try:
        pm = float(pm)
    except (ValueError, TypeError):
        return "-"

    if pm < 0:
        return pm
    if pm > 1000:
        return "-"

    # EPA breakpoints
    if pm > 350.5:
        return calc_aqi(pm, 500, 401, 500.4, 350.5)  # Hazardous
    elif pm > 250.5:
        return calc_aqi(pm, 400, 301, 350.4, 250.5)  # Hazardous
    elif pm > 150.5:
        return calc_aqi(pm, 300, 201, 250.4, 150.5)  # Very Unhealthy
    elif pm > 55.5:
        return calc_aqi(pm, 200, 151, 150.4, 55.5)   # Unhealthy
    elif pm > 35.5:
        return calc_aqi(pm, 150, 101, 55.4, 35.5)    # Unhealthy for Sensitive Groups
    elif pm > 12.1:
        return calc_aqi(pm, 100, 51, 35.4, 12.1)     # Moderate
    elif pm >= 0:
        return calc_aqi(pm, 50, 0, 12.0, 0.0)        # Good
    else:
        return "-"

def read_sensor_ids(filepath):
    ids = []
    with open(filepath, "r") as file:
        reader = csv.DictReader(file)  # This reads rows as dictionaries
        for row in reader:
            ids.append(int(row['ID']))
    return ids

def fetch_sensor_data(sensor):
    url = f"https://api.purpleair.com/v1/sensors/{sensor["ID"]}/history"
    end_time = int(time.time())
    start_time = end_time - (1 * 60 * 60)  # 1 hours ago (for redundancy)
    params = {
        "start_timestamp": start_time,
        "end_timestamp": end_time,
        "average": 10, 
        "fields": ','.join(["pm2.5_cf_1" if sensor["Location"] == "Indoor" else "pm2.5_atm", "humidity"])
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

def write_sensor_data(sensor, data):
    if not data or "data" not in data or "fields" not in data:
        print(f"No valid data to write for sensor {sensor["ID"]}")
        return

    csv_path = DATA_DIR / f"{sensor["ID"]}.csv"
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
        pm = row_dict.get("pm2.5_cf_1" if sensor["Location"] == "Indoor" else "pm2.5_atm")
        rh = row_dict.get("humidity")
        epa_pm = apply_epa_pm_correction(pm, rh)
        aqi = aqi_from_pm(epa_pm)
        
        row = {
            "timestamp": ts,
            "datetime": dt_mtn.isoformat(),
            "Raw PM2.5 (µg/m³)": pm,
            "Relative Humidity (%)": rh,
            "Raw PM2.5 (US EPA) (µg/m³)": round(epa_pm, 1),
            "US EPA PM2.5 (US EPA) (AQI)": aqi
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
    
    with open(SENSORS_FILE, "r") as file:
        sensors = csv.DictReader(file)
        for sensor in sensors:
            sensor_id = sensor['ID']
            print(f"\nFetching data for sensor {sensor_id}...")
            data = fetch_sensor_data(sensor)
            write_sensor_data(sensor, data)
            time.sleep(1)  # pauses for 1 second

if __name__ == "__main__":
    main()
