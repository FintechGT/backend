from datetime import datetime, timedelta, timezone
from jose import jwt
import os
from dotenv import load_dotenv

# Carga variables de entorno del .env
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "un_secreto_muy_largo_y_seguro")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

def make_token(user_id: int, minutes: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

if __name__ == "__main__":
    # Cambia el ID según el usuario que quieras probar
    token = make_token(user_id=1, minutes=120)
    print("Bearer", token)
