
from fastapi import FastAPI, Request, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import io
import random
from PIL import Image
import torch
import timm
import numpy as np
from torchvision import transforms
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

# -----------------------------
# GLOBAL MODEL
# -----------------------------
MODEL_URL = "https://github.com/darkmoorltd-jpg/Spectra/releases/download/v1.0-384-full/open_set_mineral_model_384_full.pt"
MODEL_PATH = "models/open_set_mineral_model_384_full.pt"

# Load model at startup
try:
    os.makedirs("models", exist_ok=True)
    if not os.path.exists(MODEL_PATH) or os.path.getsize(MODEL_PATH) < 10_000_000:
        print(f"Downloading model...")
        r = req.get(MODEL_URL, stream=True, timeout=300)
        r.raise_for_status()
        with open(MODEL_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=32768):
                if chunk:
                    f.write(chunk)
        print("Model downloaded.")
    checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    class_names = checkpoint['class_names']
    prototypes = checkpoint['prototypes']
    threshold = checkpoint['threshold']
    img_size = checkpoint['img_size']
    model = timm.create_model("vit_small_patch16_384", pretrained=False, num_classes=len(class_names))
    model.load_state_dict(checkpoint['model_state'])
    model.eval()
    feature_extractor = torch.nn.Sequential(*list(model.children())[:-1])
    feature_extractor.eval()
    proto_tensors = {cls: torch.tensor(v, dtype=torch.float32) for cls, v in prototypes.items()}
    MODEL_LOADED = True
    print("Model loaded successfully.")
except Exception as e:
    print(f"Model loading failed: {e}")
    MODEL_LOADED = False

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
        return {"error": "Model not loaded"}

    # Read image
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Preprocess
    transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    img_tensor = transform(image).unsqueeze(0)

    # Extract embedding
    with torch.no_grad():
        features = feature_extractor(img_tensor)
        embedding = features[:, 0, :].squeeze()

    def cosine_sim(a, b):
        return torch.dot(a, b) / (torch.norm(a) * torch.norm(b) + 1e-8)

    sims = {cls: cosine_sim(embedding, proto).item() for cls, proto in proto_tensors.items()}
    best_cls = max(sims, key=sims.get)
    best_sim = sims[best_cls]

    if best_sim < threshold:
        return {"mineral": "Unknown", "confidence": best_sim, "grade": None}
    else:
        # Simple grade heuristic (same as Streamlit)
        arr = np.array(image)
        brightness = arr.mean() / 255.0
        saturation = (arr.max(axis=2) - arr.min(axis=2)).mean() / 255.0
        if best_cls == "Pyrite":
            grade = 0.3 + (brightness * 0.4) + (saturation * 0.1)
        elif best_cls in ["Malachite", "Chrysocolla", "Bornite"]:
            grade = 0.2 + (saturation * 0.6) + (brightness * 0.2)
        elif best_cls == "Quartz":
            grade = 0.1 + (brightness * 0.2) + (saturation * 0.3)
        else:
            grade = 0.2 + (brightness * 0.3) + (saturation * 0.4)
        grade = max(0.1, min(0.9, grade))
        return {"mineral": best_cls, "confidence": best_sim, "grade": grade}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
