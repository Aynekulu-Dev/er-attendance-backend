import os
from datetime import datetime, timedelta, date as date_type
from typing import List
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # Token ለ 1 ቀን እንዲሰራ

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")

# የይለፍ ቃል ማመስጠሪያ እና ማረጋገጫ ረዳቶች
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# በአድሚን ቶክን ብቻ የሚሰሩ ኤፒአዮችን ለመጠበቅ (Dependency)
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


# ==================== HELPER FUNCTION TO AUTO-GENERATE VOLUNTEER ID ====================
def generate_next_volunteer_id(db: Session) -> str:
    """
    በዳታቤዝ ውስጥ የመጨረሻውን የቮለንቲየር ID (ለምሳሌ ER-004) በመፈለግ 
    ቀጣዩን ተከታታይ ID (ER-005) በራስ-ሰር የሚያመነጭ ተግባር።
    """
    # የመጨረሻውን የተመዘገበ ቮለንቲየር መፈለግ
    last_volunteer = db.query(models.Volunteer).order_by(models.Volunteer.volunteer_id.desc()).first()
    
    if not last_volunteer or not last_volunteer.volunteer_id:
        # ዳታቤዙ ባዶ ከሆነ ከመጀመሪያው ቁጥር ይጀምራል
        return "ER-001"
    
    try:
        # የመጨረሻውን ID (ለምሳሌ "ER-005") ወስዶ ከሰረዙ በኋላ ያለውን ቁጥር ይለያል
        last_id_str = last_volunteer.volunteer_id  # "ER-005"
        last_num = int(last_id_str.split("-")[1])  # 5
        next_num = last_num + 1                   # 6
        
        # አዲሱን ID በ "ER-006" ቅርፅ ያዘጋጃል
        return f"ER-{next_num:03d}"
    except (IndexError, ValueError):
        # የ ID አፃፃፉ ከተለየ በዘፈቀደ ቁጥር ስህተትን ይከላከላል
        import random
        return f"ER-{random.randint(100, 999)}"


# ==================== 1. ADMIN AUTHENTICATION ENDPOINTS ====================

# ለመጀመሪያ ጊዜ አድሚን ለመመዝገብ (Seeding / Registration)
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

# የአድሚን መግቢያ (Login) - Token ያመነጫል
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

# አዲስ ቮለንቲየር መመዝገቢያ (ID በራሱ ይመነጫል - Protected)
@app.post("/api/volunteers", response_model=schemas.VolunteerResponse)
def register_volunteer(
    volunteer: schemas.VolunteerCreate, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin) # አድሚን መሆኑን ያረጋግጣል
):
    # 1. አዲሱን መለያ ቁጥር (ID) በራስ-ሰር እናመነጫለን
    generated_id = generate_next_volunteer_id(db)
    
    # 2. የገባውን ዳታ ወደ ፎርማቱ ለመቀየር እና IDውን ለመተካት
    # (ማሳሰቢያ፦ schemas.VolunteerCreate ላይ 'volunteer_id'ን optional/ማስገባት የማይጠበቅብን ማድረግ ይመረጣል)
    volunteer_data = volunteer.dict()
    volunteer_data["volunteer_id"] = generated_id
    
    # 3. ወደ CRUD መላክ
    # crud.create_volunteer ከ schemas.VolunteerCreate ይልቅ በተሻሻለው ዳታ እንዲሰራ፡
    new_volunteer = crud.create_volunteer(db, schemas.VolunteerCreate(**volunteer_data))
    return new_volunteer

# ሙሉ የቮለንቲየሮች ዝርዝር ማምጫ (ለተመዘገበ አድሚን ብቻ የተፈቀደ - Protected)
@app.get("/api/volunteers", response_model=List[schemas.VolunteerResponse])
def read_volunteers(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin)
):
    return crud.get_volunteers(db, skip=skip, limit=limit)


# ==================== 3. ATTENDANCE ENDPOINT ====================

# የአቴንዳንስ መመዝገቢያ (ለቮለንቲየሮች መግቢያና መውጫ - Public)
@app.post("/api/attendance")
def record_attendance(request: schemas.AttendanceRequest, db: Session = Depends(get_db)):
    result = crud.record_attendance(db, request)
    
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=result["message"]
        )
        
    volunteer = crud.get_volunteer_by_id(db, request.volunteer_id)
    action_text = "የመግቢያ ሰዓትህ" if request.action == "check-in" else "የመውጫ ሰዓትህ"
    cheer_text = "መልካም የስራ ጊዜ!" if request.action == "check-in" else "ደህና እደር! እናመሰግናለን።"
    
    return {
        "status": "success",
        "message": f"ሰላም {volunteer.full_name}! {action_text} በስኬት ተመዝግቧል። {cheer_text}",
        "data": result["data"]
    }


# ==================== 4. ADMIN & ANALYTICS ENDPOINTS ====================

# የአድሚን ዳሽቦርድ የትንተና ሪፖርት (ለተመዘገበ አድሚን ብቻ የተፈቀደ - Protected)
@app.get("/api/admin/analytics", response_model=schemas.DashboardAnalytics)
def get_admin_analytics(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin)
):
    return crud.get_dashboard_analytics(db)


# የ CSV ፋይል ማውረጃ (Export Attendance Data to CSV - Protected)
@app.get("/api/admin/export-csv")
def export_attendance_csv(current_admin: models.AdminUser = Depends(get_current_admin)):
    """
    አድሚኑ በአንድ ክሊክ ሙሉውን የመገኘት ታሪክ በ CSV ፋይል አውርዶ ኮምፒውተሩ ላይ እንዲያስቀምጥ የሚፈቅድ ኤፒአይ
    """
    backup_file_path = os.path.join("backups", "attendance_backup.csv")
    
    if not os.path.exists(backup_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="እስካሁን ምንም የመገኘት ሪከርድ አልተመዘገበም!"
        )
        
    return FileResponse(
        path=backup_file_path, 
        filename=f"ethiopia_reads_attendance_{crud.date.today().isoformat()}.csv",
        media_type="text/csv"
    )