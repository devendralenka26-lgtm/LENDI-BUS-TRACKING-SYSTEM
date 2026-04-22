import os
import math
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

app = Flask(__name__, static_folder="static", static_url_path="/static")
load_dotenv()

cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins == "*":
    CORS(app)
else:
    CORS(app, origins=[x.strip() for x in cors_origins.split(",") if x.strip()])

# =========================
# CONFIGURATION
# =========================
# 1. SUPABASE_URL:
# How to find: Go to your Supabase Dashboard -> Project Settings (gear icon) -> API. Look for the "Project URL".
SUPABASE_URL = "https://mvuzpewrfbcacaysaezw.supabase.co"

# 2. SUPABASE_SERVICE_KEY:
# How to find: Go to your Supabase Dashboard -> Project Settings -> API. Look for "Project API keys" -> "service_role" secret.
# IMPORTANT: Use the 'service_role' key, not the 'anon' public key so the admin portal bypasses Row Level Security.
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im12dXpwZXdyZmJjYWNheXNhZXp3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTg3Mzg4OCwiZXhwIjoyMDkxNDQ5ODg4fQ.0HVG22FIJ641_0PJQVr4grXBTUKB4__OarVkoSdtH30"

# 3. JWT_SECRET:
# How to find: You don't need to find this anywhere. Just make up a long, random string here to encrypt sessions securely.
JWT_SECRET = "my-custom-super-secret-jwt-key"

GEOFENCE_METERS = 500  # Notify when near stop
DELAY_MINUTES = 5

sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_KEY else None

# =========================
# CACHE
# =========================
CACHE = {
    "stops": {"data": None, "updated_at": None},
}
CACHE_TTL = 60 # seconds

def get_cached_stops():
    now = datetime.now()
    if CACHE["stops"]["data"] and CACHE["stops"]["updated_at"] and (now - CACHE["stops"]["updated_at"]).total_seconds() < CACHE_TTL:
        return CACHE["stops"]["data"]
    if sb:
        stops = sb.table("stops").select("*").execute().data
        CACHE["stops"]["data"] = stops
        CACHE["stops"]["updated_at"] = now
        return stops
    return []

# =========================
# HELPERS
# =========================
def utcnow():
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.isoformat()

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            return jsonify({"error": "Token is missing or invalid"}), 401
        token = token.split(" ")[1]
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            # Inject user data into kwargs
            return f(current_user=data, *args, **kwargs)
        except Exception:
            return jsonify({"error": "Token is invalid"}), 401
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(current_user=current_user, *args, **kwargs)
    return decorated

def driver_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get("role") != "driver":
            return jsonify({"error": "Driver access required"}), 403
        return f(current_user=current_user, *args, **kwargs)
    return decorated

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def insert_alert(bus_id, message, alert_type):
    if not sb: return
    try:
        sb.table("alerts").insert({
            "bus_id": bus_id,
            "message": message,
            "type": alert_type
        }).execute()
    except Exception as e:
        print(f"Error inserting alert: {e}")

def parse_json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}

def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# =========================
# AUTHENTICATION
# =========================
@app.post("/api/login")
def login():
    if not sb:
        return jsonify({"error": "Database not configured"}), 500
    
    body = parse_json_body()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    user_res = sb.table("users").select("*").eq("email", email).execute()
    users = user_res.data
    
    if not users:
        return jsonify({"error": "Invalid credentials"}), 401
    
    user = users[0]
    
    if not check_password(password, user["password"]):
        return jsonify({"error": "Invalid credentials"}), 401
    
    # Generate JWT
    token_payload = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "bus_id": user.get("bus_id"),
        "stop_id": user.get("stop_id"),
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    
    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    
    # Strip password before returning
    del user["password"]
    
    return jsonify({
        "token": token,
        "user": user
    })

# =========================
# ADMIN APIs
# =========================
@app.post("/api/admin/users")
@token_required
@admin_required
def create_user(current_user):
    body = parse_json_body()
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password")
    name = str(body.get("name", "")).strip()
    role = str(body.get("role", "")).strip().lower()
    bus_id = body.get("bus_id")
    stop_id = body.get("stop_id")
    
    if not all([email, password, name, role]):
        return jsonify({"error": "Missing required fields"}), 400
        
    if role in ["driver", "student"] and not bus_id:
        return jsonify({"error": "Bus ID is mandatory for drivers and students."}), 400
        
    if role == "student" and not stop_id:
        return jsonify({"error": "Stop assignment is mandatory for students."}), 400
    
    hashed = hash_password(password)
    
    payload = {
        "name": name,
        "email": email,
        "password": hashed,
        "role": role,
    }
    if bus_id: payload["bus_id"] = bus_id
    if stop_id: payload["stop_id"] = stop_id
    
    try:
        res = sb.table("users").insert(payload).execute()
        return jsonify({"message": "User created", "data": res.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/admin/buses")
@token_required
@admin_required
def create_bus(current_user):
    import re
    body = parse_json_body()
    bus_number = str(body.get("bus_number", ""))
    if not re.match(r"^\d{4}$", bus_number):
        return jsonify({"error": "Bus number must be exactly 4 digits (XXXX)"}), 400

    route_id = body.get("route_id")
    total_stops = parse_int(body.get("total_stops"), 0)

    try:
        res = sb.table("buses").insert({
            "bus_number": bus_number,
            "route_id": route_id if route_id else None,
            "total_stops": total_stops
        }).execute()
        return jsonify({"message": "Bus created", "data": res.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.put("/api/admin/buses/<int:bus_id>/assign_driver")
@token_required
@admin_required
def assign_driver(current_user, bus_id):
    body = parse_json_body()
    driver_id = body.get("driver_id")
    try:
        # Update bus
        sb.table("buses").update({"driver_id": driver_id}).eq("id", bus_id).execute()
        # Update driver's bus_id
        sb.table("users").update({"bus_id": bus_id}).eq("id", driver_id).execute()
        return jsonify({"message": "Driver assigned successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/admin/routes")
@token_required
@admin_required
def create_route(current_user):
    body = parse_json_body()
    route_name = str(body.get("route_name", "")).strip()
    if not route_name:
        return jsonify({"error": "route_name is required"}), 400
    try:
        res = sb.table("routes").insert({"route_name": route_name}).execute()
        return jsonify({"message": "Route created", "data": res.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/admin/stops")
@token_required
@admin_required
def create_stop(current_user):
    import re
    body = parse_json_body()
    route_id = body.get("route_id")
    stop_name = str(body.get("stop_name", ""))
    
    if not re.match(r"^\d{4}-\d$", stop_name):
        return jsonify({"error": "Stop name must be in format XXXX-X"}), 400

    latitude = parse_float(body.get("latitude"))
    longitude = parse_float(body.get("longitude"))
    stop_order = parse_int(body.get("stop_order"), 0)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"error": "Invalid latitude/longitude"}), 400
    
    try:
        res = sb.table("stops").insert({
            "route_id": route_id,
            "stop_name": stop_name,
            "latitude": latitude,
            "longitude": longitude,
            "stop_order": stop_order
        }).execute()
        CACHE["stops"]["updated_at"] = None
        return jsonify({"message": "Stop created", "data": res.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/admin/system_data")
@token_required
@admin_required
def get_system_data(current_user):
    # Consolidate all system data for the admin dashboard map view
    try:
        buses = sb.table("buses").select("*").execute().data
        routes = sb.table("routes").select("*").execute().data
        stops = get_cached_stops()
        users = sb.table("users").select("id, name, email, role, bus_id, stop_id").execute().data
        return jsonify({"buses": buses, "routes": routes, "stops": stops, "users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# DRIVER APIs
# =========================
@app.post("/api/driver/trip/start")
@token_required
@driver_required
def start_trip(current_user):
    bus_id = current_user.get("bus_id")
    if not bus_id:
        return jsonify({"error": "Driver is not assigned to a bus"}), 400
        
    try:
        sb.table("live_locations").upsert({
            "bus_id": bus_id,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "heading": 0.0,
            "is_trip_active": True,
            "last_updated": iso(utcnow())
        }).execute()
        
        insert_alert(bus_id, "Bus trip has started.", "bus_started")
        return jsonify({"message": "Trip started successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/driver/trip/stop")
@token_required
@driver_required
def stop_trip(current_user):
    bus_id = current_user.get("bus_id")
    if not bus_id:
        return jsonify({"error": "Driver is not assigned to a bus"}), 400
        
    try:
        existing = sb.table("live_locations").select("latitude, longitude, speed, heading").eq("bus_id", bus_id).execute().data
        prev = existing[0] if existing else {}

        sb.table("live_locations").upsert({
            "bus_id": bus_id,
            "latitude": float(prev.get("latitude", 0.0)),
            "longitude": float(prev.get("longitude", 0.0)),
            "speed": float(prev.get("speed", 0.0)),
            "heading": float(prev.get("heading", 0.0)),
            "is_trip_active": False,
            "last_updated": iso(utcnow())
        }).execute()
        
        insert_alert(bus_id, "Bus trip has ended.", "info")
        return jsonify({"message": "Trip stopped successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/driver/location")
@token_required
@driver_required
def update_location(current_user):
    bus_id = current_user.get("bus_id")
    if not bus_id:
        return jsonify({"error": "Driver is not assigned to a bus"}), 400
        
    body = parse_json_body()
    lat = parse_float(body.get("latitude"), 0.0)
    lon = parse_float(body.get("longitude"), 0.0)
    speed = max(parse_float(body.get("speed"), 0.0), 0.0)
    heading = parse_float(body.get("heading"), 0.0) % 360
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "Invalid latitude/longitude"}), 400
    
    now = utcnow()
    
    try:
        # Check previous location to detect delays
        prev = sb.table("live_locations").select("last_updated").eq("bus_id", bus_id).execute().data
        
        sb.table("live_locations").upsert({
            "bus_id": bus_id,
            "latitude": lat,
            "longitude": lon,
            "speed": speed,
            "heading": heading,
            "is_trip_active": True,
            "last_updated": iso(now)
        }).execute()

        # Delay detection (No movement for X min)
        if prev and prev[0].get("last_updated"):
            last_dt = datetime.fromisoformat(prev[0]["last_updated"].replace("Z", "+00:00"))
            time_diff = (now - last_dt).total_seconds()
            
            # If speed is < 1 for 5 minutes, log a delay
            if speed < 1.0 and time_diff >= (DELAY_MINUTES * 60):
                # Anti-spam: Only insert if we haven't alerted for this exact bus recently
                recent_delays = sb.table("delays").select("id").eq("bus_id", bus_id).gte("created_at", iso(now - timedelta(minutes=DELAY_MINUTES))).execute().data
                if not recent_delays:
                    sb.table("delays").insert({
                        "bus_id": bus_id,
                        "delay_time": int(time_diff)
                    }).execute()
                    insert_alert(bus_id, f"Bus is delayed (stopped for {DELAY_MINUTES} minutes)", "delay")

        # Check geofences for nearby stops. 
        stops = get_cached_stops()
        for st in stops:
            d = haversine_m(lat, lon, st["latitude"], st["longitude"])
            if d <= GEOFENCE_METERS:
                # Anti-spam: check if recently alerted
                recents = sb.table("alerts").select("id").eq("bus_id", bus_id).eq("type", "near_stop").gte("created_at", iso(now - timedelta(minutes=10))).execute().data
                if not recents:
                    insert_alert(bus_id, f"Bus is arriving near {st['stop_name']} soon (distance {int(d)}m)", "near_stop")

        return jsonify({"message": "Location updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/driver/emergency")
@token_required
@driver_required
def emergency(current_user):
    bus_id = current_user.get("bus_id")
    if not bus_id:
        return jsonify({"error": "Driver is not assigned to a bus"}), 400
    
    insert_alert(bus_id, "EMERGENCY: The driver has reported an emergency. Bus is stopped.", "emergency")
    return jsonify({"message": "Emergency alert broadcasted."})

# =========================
# STUDENT APIs
# =========================
@app.get("/api/student/ride_status")
@token_required
def ride_status(current_user):
    """
    Returns entire payload needed for the student dashboard.
    """
    if current_user.get("role") != "student":
        return jsonify({"error": "Student access required"}), 403

    bus_id = current_user.get("bus_id")
    stop_id = current_user.get("stop_id")
    
    if not bus_id:
        return jsonify({"error": "No bus assigned to student"}), 400
        
    try:
        # Get live location
        live_loc_resp = sb.table("live_locations").select("*").eq("bus_id", bus_id).execute().data
        live_loc = live_loc_resp[0] if live_loc_resp else None
        
        # Get Bus and Route info
        bus_resp = sb.table("buses").select("bus_number, route_id").eq("id", bus_id).execute().data
        bus = bus_resp[0] if bus_resp else None
        
        route_id = bus["route_id"] if bus else None
        stops = []
        target_stop = None
        if route_id:
            all_stops = get_cached_stops()
            stops = [s for s in all_stops if s["route_id"] == route_id]
            stops.sort(key=lambda x: x["stop_order"])
            if stop_id:
                target_stop = next((s for s in stops if s["id"] == stop_id), None)
        
        # Calculate ETA
        eta_seconds = 0
        distance_m = 0
        if live_loc and target_stop and live_loc.get("is_trip_active"):
            distance_m = haversine_m(live_loc["latitude"], live_loc["longitude"], target_stop["latitude"], target_stop["longitude"])
            speed_mps = max(live_loc.get("speed", 0.0), 5.0) # Assume at least 5m/s (18km/h) for ETA if 0 to avoid Infinity
            eta_seconds = distance_m / speed_mps
        
        # Get recent alerts for this bus
        alerts = sb.table("alerts").select("*").eq("bus_id", bus_id).order("created_at", desc=True).limit(5).execute().data
        
        return jsonify({
            "live_location": live_loc,
            "bus": bus,
            "target_stop": target_stop,
            "stops": stops,
            "eta_seconds": int(eta_seconds),
            "distance_m": int(distance_m),
            "alerts": alerts
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "db_configured": bool(sb),
        "timestamp": iso(utcnow())
    })


# =========================
# STATIC ASSETS (FRONTEND)
# =========================
@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/<path:path>")
def static_files(path):
    if os.path.exists(os.path.join("static", path)):
        return send_from_directory("static", path)
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5900")),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )