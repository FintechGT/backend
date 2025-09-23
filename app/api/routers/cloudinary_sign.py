import time, hashlib
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings

router = APIRouter(prefix="/cloudinary", tags=["cloudinary"])

@router.get("/ping")
def ping():
    return {"ok": True}

@router.get("/debug")
def cloudinary_debug():
    # No exponemos los valores crudos, solo “ok” y longitud del secreto
    return {
        "cloud_name_ok": bool(settings.CLOUDINARY_CLOUD_NAME),
        "api_key_ok": bool(settings.CLOUDINARY_API_KEY),
        "api_secret_len": len(settings.CLOUDINARY_API_SECRET or "")
    }

@router.get("/signature")
def get_signature(folder: str = Query("pignoraticios/solicitudes", min_length=1)):
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        raise HTTPException(status_code=500, detail="Cloudinary no está configurado en el servidor")

    timestamp = int(time.time())
    to_sign = f"folder={folder}&timestamp={timestamp}{settings.CLOUDINARY_API_SECRET}"
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    return {
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
        "api_key": settings.CLOUDINARY_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "folder": folder,
    }
