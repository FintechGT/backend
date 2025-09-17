from sqlalchemy.orm import Session
from app.db.models.user import User
from app.schemas.auth import UserRegister
from app.utils.hashing import hash_password  

def create_user(user_data: UserRegister, db: Session):
    user = User(
        nombre=user_data.nombre,
        email=user_data.email,
        password=hash_password(user_data.password)  
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
