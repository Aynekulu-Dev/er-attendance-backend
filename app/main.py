import os
from datetime import datetime, timedelta
from typing import List
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import engine, Base, get_db, SessionLocal
from . import models, schemas, crud

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Ethiopia Reads Attendance API",
    docs_url=None,      # /docs (Swagger UI) ሙሉ በሙሉ ጠፍቷል
    redoc_url=None,     # /redoc ሙሉ በሙሉ ጠፍቷል
    openapi_url=None,   # /openapi.json (ራው schema) ሙሉ በሙሉ ጠፍቷል
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SECURITY ---
SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_KEY_FOR_ETHIOPIA_READS_123!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")


def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401)
        admin = db.query(models.AdminUser).filter(models.AdminUser.username == username).first()
        if admin is None:
            raise HTTPException(status_code=401)
        return admin
    except JWTError:
        raise HTTPException(status_code=401)


@app.on_event("startup")
def create_default_admin():
    db = SessionLocal()
    try:
        existing_admin = db.query(models.AdminUser).first()
        if not existing_admin:
            default_username = os.getenv("ADMIN_USERNAME", "admin")
            default_password = os.getenv("ADMIN_PASSWORD", "changeme123")
            hashed = pwd_context.hash(default_password)
            db.add(models.AdminUser(username=default_username, hashed_password=hashed))
            db.commit()
            print(f"[INFO] Default admin ተፈጥሯል -> username: {default_username}")
    finally:
        db.close()


def _generate_next_volunteer_id(db: Session) -> str:
    last = db.query(models.Volunteer).order_by(models.Volunteer.id.desc()).first()
    if not last:
        return "ER-001"
    last_number = int(last.volunteer_id.split("-")[1])
    return f"ER-{(last_number + 1):03d}"


def _extract_client_info(request: Request) -> tuple[str, str]:
    """
    Render (እና አብዛኛው cloud host) ከፊት ለፊት reverse proxy ስላለው፣
    request.client.host ብቻ ብንጠቀም የ Render ውስጣዊ proxy IP ነው የምናገኘው እንጂ
    እውነተኛውን የተጠቃሚ IP አይደለም። ስለዚህ መጀመሪያ X-Forwarded-For ን እንፈትሻለን፣
    ከሌለ ብቻ ወደ request.client.host እንመለሳለን።
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For: "client_ip, proxy1_ip, proxy2_ip" - የመጀመሪያው እውነተኛው client ነው
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    device = request.headers.get("user-agent", "unknown")
    return ip, device


# --- ENDPOINTS ---

@app.get("/")
def root():
    return {"message": "Ethiopia Reads Attendance API is running."}


@app.post("/api/admin/login", response_model=schemas.Token)
def login_admin(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = db.query(models.AdminUser).filter(models.AdminUser.username == form_data.username).first()
    if not admin or not pwd_context.verify(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="የተጠቃሚ ስም ወይም የይለፍ ቃል ትክክል አይደለም። እንደገና ሞክር።")

    access_token = jwt.encode(
        {"sub": admin.username, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/volunteers", response_model=schemas.VolunteerRegisterResponse)
def register_volunteer(
    volunteer: schemas.VolunteerCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    new_id = _generate_next_volunteer_id(db)
    new_vol = crud.create_volunteer(db, volunteer, new_id)

    return {
        "status": "success",
        "message": f"{new_vol.full_name} በተሳካ ሁኔታ ተመዝግቧል! የቮለንቲየር መታወቂያ፡ {new_vol.volunteer_id}",
        "data": new_vol,
    }


@app.get("/api/volunteers", response_model=List[schemas.VolunteerResponse])
def read_volunteers(db: Session = Depends(get_db), current_admin=Depends(get_current_admin)):
    return db.query(models.Volunteer).all()


@app.post("/api/attendance", response_model=schemas.AttendanceActionResponse)
def record_attendance(
    payload: schemas.AttendanceRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, device_info = _extract_client_info(request)
    return crud.record_attendance(db, payload, ip_address=ip_address, device_info=device_info)


@app.get("/api/admin/analytics", response_model=schemas.DashboardAnalytics)
def get_analytics(db: Session = Depends(get_db), current_admin=Depends(get_current_admin)):
    return crud.get_dashboard_analytics(db)


# NEW: attendance log with IP/device - admin uses this to spot "friend used my ID" cases
@app.get("/api/admin/attendance-log", response_model=List[schemas.AttendanceLogRow])
def get_attendance_log(db: Session = Depends(get_db), current_admin=Depends(get_current_admin)):
    return crud.get_attendance_log(db)


@app.get("/api/admin/export-csv")
def export_csv(current_admin=Depends(get_current_admin)):
    if not os.path.exists("backups/attendance_backup.csv"):
        raise HTTPException(status_code=404, detail="እስካሁን የተመዘገበ የመገኘት (attendance) ዳታ የለም።")
    return FileResponse("backups/attendance_backup.csv", media_type="text/csv", filename="attendance.csv")