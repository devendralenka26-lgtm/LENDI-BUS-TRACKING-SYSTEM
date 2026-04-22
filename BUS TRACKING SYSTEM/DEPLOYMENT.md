# Bus Tracking System Deployment Guide

## 1) Prerequisites
- Python 3.10+ installed
- Supabase project created
- Database tables created from `setup.sql`

## 2) Environment setup
1. Copy `.env.example` to `.env`
2. Fill required values:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `JWT_SECRET` (long random string)
3. For production, set `FLASK_DEBUG=false`
4. Optional: set `CORS_ORIGINS` to your frontend domain(s), comma-separated

## 3) Install dependencies
```bash
pip install -r requirements.txt
```

## 4) Run locally
```bash
python app.py
```
- App runs on `http://localhost:5900` by default
- Health check: `GET /health`

## 5) Production deployment (recommended with Gunicorn)

Install Gunicorn:
```bash
pip install gunicorn
```

Run:
```bash
gunicorn -w 2 -k gthread -b 0.0.0.0:5900 app:app
```

Notes:
- Keep `FLASK_DEBUG=false`
- Use HTTPS via reverse proxy (Nginx, Cloudflare, or hosting platform SSL)
- Do not commit `.env` to git

## 6) Deploy options
- **Render / Railway / Fly.io**: set env vars in dashboard and start command:
  - `gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT app:app`
- **VPS + Nginx**:
  - Run Gunicorn as systemd service
  - Configure Nginx reverse proxy to Gunicorn
  - Enable SSL cert (Let's Encrypt)

## 7) Post-deploy checklist
- `GET /health` returns `status: ok`
- Login works for admin/driver/student
- Driver can start trip and push location
- Student sees live updates and offline fallback states
- Admin CRUD flows work for users/routes/buses/stops
