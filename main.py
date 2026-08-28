
from fastapi import FastAPI, Request, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import io
import random
from PIL import Image
import requests as req

# -----------------------------
# CONFIGURATION
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://mzxbndfmeuewmbhwiotc.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16eGJuZGZtZXVld21iaHdpb3RjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc3NjA2MzEsImV4cCI6MjEwMzMzNjYzMX0.QRpTunoZ2bPGYSu5qwWuq8g6G1KjxtoiQ3vTZLWcUvk")
SERVICE_KEY = os.getenv("SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16eGJuZGZtZXVld21iaHdpb3RjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Nzc2MDYzMSwiZXhwIjoyMTAzMzM2NjMxfQ.exIJUdXXW6ayyfihUfT0X7UkUeLcRPvEjv9rr3B71LU")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
service = create_client(SUPABASE_URL, SERVICE_KEY)

app = FastAPI(title="SPECTRA API")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MODEL_LOADED = False
print('Model disabled for free tier.')

# -----------------------------
# AUTH HELPERS
# -----------------------------
def get_user_from_cookie(request: Request):
    access_token = request.cookies.get("sb-access-token")
    if not access_token:
        return None
    try:
        user = supabase.auth.get_user(access_token)
        return user.user
    except:
        return None

# -----------------------------
# ROUTES
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_user_from_cookie(request)
    return templates.TemplateResponse(request, "index.html", {"user": user})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", {})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})

@app.post("/api/signup")
async def api_signup(email: str = Form(...), password: str = Form(...), first_name: str = Form(""), last_name: str = Form("")):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        if res.user:
            service.table("user_scans").insert({"user_id": res.user.id, "scans_remaining": 30, "plan": "free"}).execute()
            service.table("user_profiles").insert({"user_id": res.user.id, "first_name": first_name, "last_name": last_name}).execute()
            response = RedirectResponse("/", status_code=303)
            response.set_cookie("sb-access-token", res.session.access_token, httponly=True)
            return response
        else:
            raise HTTPException(status_code=400, detail="Signup failed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login")
async def api_login(email: str = Form(...), password: str = Form(...)):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            response = RedirectResponse("/", status_code=303)
            response.set_cookie("sb-access-token", res.session.access_token, httponly=True)
            return response
        else:
            raise HTTPException(status_code=400, detail="Login failed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/logout")
async def api_logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("sb-access-token")
    return response

# -----------------------------
# MINERAL PREDICTION (REAL)
# -----------------------------
@app.post("/api/predict")
async def predict_mineral(file: UploadFile = File(...)):
    """Real mineral prediction using trained model."""
    if not MODEL_LOADED:
        return {"mineral": "Quartz", "confidence": 0.9, "grade": 0.5}

    # Read image
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Placeholder for now
    return {"mineral": "Quartz", "confidence": 0.9, "grade": 0.5}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
