import os
from datetime import datetime, timedelta
from typing import List
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import engine, Base, get_db
from . import models, schemas, crud

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ethiopia Reads Attendance API")

# --- CORS CONFIGURATION ---
# አዝራሮች እንዲሰሩ ይህ በጣም አስፈላጊ ነው
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # ፍሮንትኤንድህ ያለበትን አድራሻ ብቻ መፍቀድ ትችላለህ
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SECURITY ---
SECRET_KEY = "SUPER_SECRET_KEY_FOR_ETHIOPIA_READS_123!"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")

def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise HTTPException(status_code=401)
        admin = db.query(models.AdminUser).filter(models.AdminUser.username == username).first()
        if admin is None: raise HTTPException(status_code=401)
        return admin
    except JWTError:
        raise HTTPException(status_code=401)

# --- ENDPOINTS ---

@app.post("/api/admin/login", response_model=schemas.Token)
def login_admin(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = db.query(models.AdminUser).filter(models.AdminUser.username == form_data.username).first()
    if not admin or not pwd_context.verify(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = jwt.encode({"sub": admin.username, "exp": datetime.utcnow() + timedelta(days=1)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/volunteers", response_model=schemas.VolunteerResponse)
def register_volunteer(volunteer: schemas.VolunteerCreate, db: Session = Depends(get_db), current_admin = Depends(get_current_admin)):
    # ID generator logic (ከዚህ ቀደም እንደነበረው)
    last = db.query(models.Volunteer).order_by(models.Volunteer.volunteer_id.desc()).first()
    new_id = f"ER-{(int(last.volunteer_id.split('-')[1]) + 1):03d}" if last else "ER-001"
    
    new_vol = models.Volunteer(volunteer_id=new_id, full_name=volunteer.full_name, phone_number=volunteer.phone_number, team=volunteer.team)
    db.add(new_vol)
    db.commit()
    db.refresh(new_vol)
    return new_vol

@app.get("/api/volunteers", response_model=List[schemas.VolunteerResponse])
def read_volunteers(db: Session = Depends(get_db), current_admin = Depends(get_current_admin)):
    return db.query(models.Volunteer).all()

@app.post("/api/attendance")
def record_attendance(request: schemas.AttendanceRequest, db: Session = Depends(get_db)):
    return crud.record_attendance(db, request)

@app.get("/api/admin/analytics")
def get_analytics(db: Session = Depends(get_db), current_admin = Depends(get_current_admin)):
    return crud.get_dashboard_analytics(db)

@app.get("/api/admin/export-csv")
def export_csv(current_admin = Depends(get_current_admin)):
    return FileResponse("backups/attendance_backup.csv", media_type="text/csv", filename="attendance.csv")