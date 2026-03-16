import os
import sqlite3
import random
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 1. Load configuration from .env
load_dotenv()

app = Flask(__name__)

# 2. Assign secrets from .env
API_KEY = os.getenv('MAINT_API_KEY')
app.secret_key = os.getenv('FLASK_SECRET', 'drt-default-fallback-key')

# 3. Define Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "drt_fleet.db")

# 4. Global Maintenance Specs
PART_SPECS = {
    "Oil Filter": {"interval": 20000, "cost": 150},
    "Fuel Filter": {"interval": 35000, "cost": 225},
    "Air Filter": {"interval": 45000, "cost": 110},
    "Brake Pads": {"interval": 75000, "cost": 850},
    "Transmission": {"interval": 120000, "cost": 1200}
}
KM_PER_DAY = 327.8 

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    conn = get_db_connection()

    # Check if the "Connect Live" toggle is active in the DB
    sync_status = conn.execute("SELECT sync_on FROM system_state").fetchone()
    sync_on = sync_status['sync_on'] if sync_status else 0
    
    db_rows = conn.execute("SELECT * FROM vehicles").fetchall()
    conn.close()

    fleet_data, immediate_parts, proactive_parts, six_month_parts = [], {}, {}, {}
    monthly_budget, six_month_budget = 0, 0

    for row in db_rows:
        bus_id = row['vehicle_id']

        # Simulated logic for km if not live, otherwise use live_km from DB
        bus_num = int(''.join(filter(str.isdigit, bus_id or '0')))
        current_km = row['live_km'] if sync_on == 1 else (bus_num * 1650) % 120000
        
        bus_checklist = []
        bus_cost = 0
        days_to_service = 999
        
        for name, spec in PART_SPECS.items():
            next_due = ((int(current_km) // spec['interval']) + 1) * spec['interval']
            days_left = round((next_due - current_km) / KM_PER_DAY)
            
            if days_left < days_to_service: days_to_service = days_left

            if days_left <= 30:
                bus_cost += spec['cost']
                monthly_budget += spec['cost']
                bus_checklist.append(name)
                
                if days_left <= 5:
                    immediate_parts[name] = immediate_parts.get(name, 0) + 1
                else:
                    proactive_parts[name] = proactive_parts.get(name, 0) + 1

            # Strategic 6-month forecast
            future_km = current_km + (KM_PER_DAY * 180)
            occ = int(future_km // spec['interval']) - int(current_km // spec['interval'])
            six_month_parts[name] = six_month_parts.get(name, 0) + max(0, occ)
            six_month_budget += (max(0, occ) * spec['cost'])

        fleet_data.append({
            "id": bus_id, 
            "km": round(current_km, 1), 
            "days_left": days_to_service,
            "due_date": (datetime.now() + timedelta(days=max(0, days_to_service))).strftime('%b %d'),
            "status": "Urgent" if days_to_service <= 5 else "Proactive" if days_to_service <= 30 else "Healthy",
            "ticket_cost": bus_cost, 
            "parts_needed": bus_checklist,
            "is_live": True if sync_on == 1 else False # This triggers the pulsing dot
        })

    return jsonify({
        "fleet": fleet_data, 
        "immediate_parts": immediate_parts, 
        "proactive_parts": proactive_parts, 
        "six_month_parts": six_month_parts,
        "budget": {"monthly": monthly_budget, "six_month": six_month_budget}
    })

@app.route('/api/sync_toggle', methods=['POST'])
def sync_toggle():
    status = request.json.get('active', 0)
    conn = get_db_connection()
    conn.execute("UPDATE system_state SET sync_on = ?", (status,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "sync_on": status})

@app.route('/api/comments/<vehicle_id>')
def get_comments(vehicle_id):
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM service_logs WHERE vehicle_id = ? ORDER BY timestamp DESC", (vehicle_id,)).fetchall()
    conn.close()
    return jsonify([dict(log) for log in logs])

@app.route('/api/save_comment', methods=['POST'])
def save_comment():
    data = request.json
    conn = get_db_connection()
    conn.execute("INSERT INTO service_logs (vehicle_id, engineer_name, comment, timestamp) VALUES (?, ?, ?, ?)",
                 (data['vehicle_id'], data['engineer_name'], data['comment'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':

    # Running on port 8010 as requested
    app.run(debug=True, port=8010)