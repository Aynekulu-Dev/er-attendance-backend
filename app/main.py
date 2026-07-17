import os
from datetime import datetime, timedelta, date as date_type
from typing import List
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse  # 1. RedirectResponse ታክሏል
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import engine, Base, get_db
from . import models, schemas, crud

# የዳታቤዝ ሰንጠረዦቹን መፍጠር
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ethiopia Reads Attendance API with Secure Admin Login")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SECURITY CONFIGURATIONS ---
SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_KEY_FOR_ETHIOPIA_READS_123!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="የአድሚን ማረጋገጫ (Token) ልክ አይደለም ወይም ጊዜው አልፏል!",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    admin = db.query(models.AdminUser).filter(models.AdminUser.username == username).first()
    if admin is None:
        raise credentials_exception
    return admin

# ==================== ROOT REDIRECT ====================
@app.get("/", include_in_schema=False)
def root():
    """ዋናውን ሊንክ ሲከፍቱ በቀጥታ ወደ API Documentation ይወስዳል"""
    return RedirectResponse(url="/docs")

# ==================== HELPER FUNCTION TO AUTO-GENERATE VOLUNTEER ID ====================
def generate_next_volunteer_id(db: Session) -> str:
    last_volunteer = db.query(models.Volunteer).order_by(models.Volunteer.volunteer_id.desc()).first()
    if not last_volunteer or not last_volunteer.volunteer_id:
        return "ER-001"
    try:
        last_id_str = last_volunteer.volunteer_id
        last_num = int(last_id_str.split("-")[1])
        next_num = last_num + 1
        return f"ER-{next_num:03d}"
    except (IndexError, ValueError):
        import random
        return f"ER-{random.randint(100, 999)}"

# ==================== 1. ADMIN AUTHENTICATION ENDPOINTS ====================
@app.post("/api/admin/register", response_model=schemas.Token)
def register_admin(admin_data: schemas.AdminLogin, db: Session = Depends(get_db)):
    existing_admin = db.query(models.AdminUser).filter(models.AdminUser.username == admin_data.username).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="ይህ የአድሚን ስም ቀድሞ ተወስዷል!")
    hashed_pw = get_password_hash(admin_data.password)
    new_admin = models.AdminUser(username=admin_data.username, hashed_password=hashed_pw)
    db.add(new_admin)
    db.commit()
    access_token = create_access_token(data={"sub": new_admin.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/admin/login", response_model=schemas.Token)
def login_admin(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = db.query(models.AdminUser).filter(models.AdminUser.username == form_data.username).first()
    if not admin or not verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="የተሳሳተ የተጠቃሚ ስም (Username) ወይም የይለፍ ቃል (Password)!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": admin.username})
    return {"access_token": access_token, "token_type": "bearer"}

# ==================== 2. VOLUNTEER ENDPOINTS ====================
@app.post("/api/volunteers", response_model=schemas.VolunteerResponse)
def register_volunteer(volunteer: schemas.VolunteerCreate, db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_admin)):
    generated_id = generate_next_volunteer_id(db)
    volunteer_data = volunteer.dict()
    volunteer_data["volunteer_id"] = generated_id
    new_volunteer = crud.create_volunteer(db, schemas.VolunteerCreate(**volunteer_data))
    return new_volunteer

@app.get("/api/volunteers", response_model=List[schemas.VolunteerResponse])
def read_volunteers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_admin)):
    return crud.get_volunteers(db, skip=skip, limit=limit)

# ==================== 3. ATTENDANCE ENDPOINT ====================
@app.post("/api/attendance")
def record_attendance(request: schemas.AttendanceRequest, db: Session = Depends(get_db)):
    result = crud.record_attendance(db, request)
    if result["status"] == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    volunteer = crud.get_volunteer_by_id(db, request.volunteer_id)
    return {
        "status": "success",
        "message": f"ሰላም {volunteer.full_name}! መዝገብህ ተመዝግቧል።",
        "data": result["data"]
    }

# ==================== 4. ADMIN & ANALYTICS ENDPOINTS ====================
@app.get("/api/admin/analytics", response_model=schemas.DashboardAnalytics)
def get_admin_analytics(db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_admin)):
    return crud.get_dashboard_analytics(db)

@app.get("/api/admin/export-csv")
def export_attendance_csv(current_admin: models.AdminUser = Depends(get_current_admin)):
    backup_file_path = os.path.join("backups", "attendance_backup.csv")
    if not os.path.exists(backup_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ሪከርድ የለም!")
    return FileResponse(path=backup_file_path, filename="attendance.csv", media_type="text/csv")