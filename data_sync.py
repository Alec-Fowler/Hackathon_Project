import requests
import sqlite3
from google.transit import gtfs_realtime_pb2
from datetime import datetime
import os

# Paths and API configuration
current_folder = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(current_folder, "drt_fleet.db")

API_KEY = "transit_publicapi_v3_90d8059bffd44b37103ab6d2049da5583b01d4696579590e6d706540afed5cb5"
URL = "https://drtonline.durhamregiontransit.com/gtfsrealtime/VehiclePositions"

# Main sync routine: fetch feed, parse it, and write latest bus positions
def run_sync():
    # Build authorization headers for the GTFS realtime API request
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        # Fetch and decode the protobuf feed payload
        response = requests.get(URL, headers=headers, timeout=10)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        # Open local SQLite database and ensure vehicle table exists
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vehicles (
                vehicle_id TEXT PRIMARY KEY,
                last_lat REAL,
                last_lon REAL,
                last_updated TEXT,
                total_km REAL DEFAULT 0
            )
        ''')

        # Upsert each vehicle's latest position and timestamp
        count = 0
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                v = entity.vehicle
                bus_id = v.vehicle.id or v.vehicle.label or f"BUS-{count}"
                cursor.execute('''
                    INSERT INTO vehicles (vehicle_id, last_lat, last_lon, last_updated)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(vehicle_id) DO UPDATE SET
                        last_lat = EXCLUDED.last_lat,
                        last_lon = EXCLUDED.last_lon,
                        last_updated = EXCLUDED.last_updated
                ''', (bus_id, v.position.latitude, v.position.longitude, datetime.now().isoformat()))
                count += 1

        conn.commit()
        conn.close()
        print(f"Success: Updated {count} unique buses.")
    except Exception as e:
        print(f"Error: {e}")

# Script entry point for manual execution
if __name__ == "__main__":
    run_sync()