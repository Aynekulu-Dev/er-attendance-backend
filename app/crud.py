import os
import csv
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from . import models, schemas
import math

# --- 1. GEOFENCING CONSTANTS ---
COMPANY_LAT = float(os.getenv("COMPANY_LAT", "9.012345"))
COMPANY_LON = float(os.getenv("COMPANY_LON", "38.754321"))
ALLOWED_RADIUS_METERS = float(os.getenv("ALLOWED_RADIUS_METERS", "5000"))

# --- 2. ራስ-ሰር የ CSV BACKUP ፎልደር ማዘጋጃ ---
BACKUP_DIR = "backups"
BACKUP_FILE = os.path.join(BACKUP_DIR, "attendance_backup.csv")


def append_to_csv_backup(attendance_record: models.Attendance, volunteer_name: str, team: str):
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        file_exists = os.path.exists(BACKUP_FILE)

        with open(BACKUP_FILE, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow([
                    "Backup_Timestamp", "Attendance_ID", "Volunteer_ID", "Full_Name", "Team",
                    "Date", "Week_Number", "Check_In_Time", "Check_In_IP", "Check_In_Device",
                    "Check_Out_Time", "Check_Out_IP", "Check_Out_Device", "Status"
                ])

            writer.writerow([
                datetime.utcnow().isoformat(),
                attendance_record.id,
                attendance_record.volunteer_id,
                volunteer_name,
                team,
                attendance_record.date,
                attendance_record.week_number,
                attendance_record.check_in_time.isoformat() if attendance_record.check_in_time else "",
                attendance_record.check_in_ip or "",
                attendance_record.check_in_device or "",
                attendance_record.check_out_time.isoformat() if attendance_record.check_out_time else "",
                attendance_record.check_out_ip or "",
                attendance_record.check_out_device or "",
                attendance_record.status
            ])
    except Exception as e:
        print(f"Error writing to CSV backup: {e}")


# --- 3. የርቀት ማስያ ሎጂክ (Haversine Formula) ---
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# --- 4. የ 7 ሳምንት ሰርተፍኬት ብቁነት መፈተሻ ሎጂክ ---
def update_certificate_eligibility(db: Session, volunteer_id: str):
    attendances = db.query(models.Attendance).filter(
        models.Attendance.volunteer_id == volunteer_id,
        models.Attendance.status == "Present"
    ).all()

    weekly_presence = {week: 0 for week in range(1, 8)}
    for record in attendances:
        if record.week_number in weekly_presence:
            weekly_presence[record.week_number] += 1

    is_eligible = True
    for week, count in weekly_presence.items():
        if count < 3:
            is_eligible = False
            break

    volunteer = db.query(models.Volunteer).filter(models.Volunteer.volunteer_id == volunteer_id).first()
    if volunteer:
        volunteer.is_eligible_for_certificate = is_eligible
        db.commit()
        db.refresh(volunteer)


# --- 5. የሰመር ካምፕ የሳምንት ቁጥር ማስያ ---
def get_current_week_number(db: Session) -> int:
    first_volunteer = db.query(models.Volunteer).order_by(models.Volunteer.registered_at.asc()).first()
    if not first_volunteer:
        return 1

    start_date = first_volunteer.registered_at.date()
    today = date.today()
    days_passed = (today - start_date).days

    week_number = (days_passed // 7) + 1
    return min(max(week_number, 1), 7)


# --- 6. VOLUNTEER CRUD ---
def create_volunteer(db: Session, volunteer: schemas.VolunteerCreate, volunteer_id: str):
    db_volunteer = models.Volunteer(
        volunteer_id=volunteer_id,
        full_name=volunteer.full_name,
        phone_number=volunteer.phone_number,
        team=volunteer.team
    )
    db.add(db_volunteer)
    db.commit()
    db.refresh(db_volunteer)
    return db_volunteer


def get_volunteers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Volunteer).offset(skip).limit(limit).all()


def get_volunteer_by_id(db: Session, volunteer_id: str):
    return db.query(models.Volunteer).filter(models.Volunteer.volunteer_id == volunteer_id).first()


# --- 7. ATTENDANCE CRUD & AUTO-BACKUP INTEGRATION ---
def record_attendance(
    db: Session,
    request: schemas.AttendanceRequest,
    ip_address: str,
    device_info: str,
):
    """
    Check-in/Check-out መዝጋቢ። IP/device በ FastAPI layer ላይ (main.py) ከ Request object
    ራሱ የተወሰደ ነው - client በፍጹም ራሱን IP/device አድርጎ አይላክም (ማጭበርበርን ለመከላከል)።

    IP/device ብቻውን ማጭበርበርን ራሱ አያግድም (ተመሳሳይ WiFi ላይ ያሉ ሁለት ሰዎች ተመሳሳይ IP ሊኖራቸው
    ይችላል) - ግን admin ለክትትል/ማጣራት እንዲጠቀምበት metadata ሆኖ ይመዘገባል።
    """
    volunteer = get_volunteer_by_id(db, request.volunteer_id)
    if not volunteer:
        return {
            "status": "error",
            "message": "ይህ የቮለንቲየር መታወቂያ (ID) አልተመዘገበም! እባክህ ID ን አረጋግጥ።",
            "data": None,
        }

    distance = calculate_distance(request.user_lat, request.user_lon, COMPANY_LAT, COMPANY_LON)
    if distance > ALLOWED_RADIUS_METERS:
        return {
            "status": "error",
            "message": f"ከተፈቀደው የካምፕ ክልል ውጭ ነህ! ካለህበት ርቀት፡ {int(distance)} ሜትር (የተፈቀደው፡ {int(ALLOWED_RADIUS_METERS)} ሜትር)",
            "data": None,
        }

    today_str = date.today().isoformat()
    current_week = get_current_week_number(db)

    attendance_record = db.query(models.Attendance).filter(
        models.Attendance.volunteer_id == request.volunteer_id,
        models.Attendance.date == today_str
    ).first()

    if request.action == "check-in":
        if attendance_record:
            return {
                "status": "error",
                "message": "ዛሬ ቀድመህ Check-in አድርገሃል!",
                "data": schemas.AttendanceResponse.model_validate(attendance_record),
            }

        attendance_record = models.Attendance(
            volunteer_id=request.volunteer_id,
            date=today_str,
            week_number=current_week,
            check_in_time=datetime.utcnow(),
            check_in_ip=ip_address,
            check_in_device=device_info,
            status="Present"
        )
        db.add(attendance_record)
        db.commit()
        db.refresh(attendance_record)
        friendly_message = f"እንኳን ደህና መጣህ፣ {volunteer.full_name}! Check-in በተሳካ ሁኔታ ተመዝግቧል።"

    elif request.action == "check-out":
        if not attendance_record:
            return {
                "status": "error",
                "message": "መጀመሪያ Check-in ማድረግ አለብህ!",
                "data": None,
            }
        if attendance_record.check_out_time:
            return {
                "status": "error",
                "message": "ዛሬ ቀድመህ Check-out አድርገሃል!",
                "data": schemas.AttendanceResponse.model_validate(attendance_record),
            }

        attendance_record.check_out_time = datetime.utcnow()
        attendance_record.check_out_ip = ip_address
        attendance_record.check_out_device = device_info
        db.commit()
        db.refresh(attendance_record)
        friendly_message = f"ደህና ሰንብት፣ {volunteer.full_name}! Check-out በተሳካ ሁኔታ ተመዝግቧል።"

    else:
        return {
            "status": "error",
            "message": "action 'check-in' ወይም 'check-out' ብቻ መሆን አለበት።",
            "data": None,
        }

    update_certificate_eligibility(db, request.volunteer_id)
    append_to_csv_backup(attendance_record, volunteer.full_name, volunteer.team)

    return {
        "status": "success",
        "message": friendly_message,
        "data": schemas.AttendanceResponse.model_validate(attendance_record),
    }


# --- 8. DASHBOARD ANALYTICS ---
def get_dashboard_analytics(db: Session) -> schemas.DashboardAnalytics:
    total_volunteers = db.query(models.Volunteer).count()

    today_str = date.today().isoformat()

    today_checkins = db.query(models.Attendance).filter(
        models.Attendance.date == today_str,
        models.Attendance.check_in_time.isnot(None),
    ).count()

    today_checkouts = db.query(models.Attendance).filter(
        models.Attendance.date == today_str,
        models.Attendance.check_out_time.isnot(None),
    ).count()

    certified_volunteers_count = db.query(models.Volunteer).filter(
        models.Volunteer.is_eligible_for_certificate == True
    ).count()

    trend_data = db.query(
        models.Attendance.date
    ).filter(models.Attendance.status == "Present").all()

    daily_trend = {}
    for record in trend_data:
        daily_trend[record.date] = daily_trend.get(record.date, 0) + 1

    daily_stats_list = [
        schemas.DailyStats(date=d, present_count=c)
        for d, c in sorted(daily_trend.items())
    ]

    volunteers = db.query(models.Volunteer.team).all()
    team_counts = {}
    for v in volunteers:
        team_counts[v.team] = team_counts.get(v.team, 0) + 1

    team_stats_list = [
        schemas.TeamStats(team_name=t, count=c)
        for t, c in team_counts.items()
    ]

    return schemas.DashboardAnalytics(
        total_volunteers=total_volunteers,
        today_checkins=today_checkins,
        today_checkouts=today_checkouts,
        certified_volunteers_count=certified_volunteers_count,
        daily_attendance_trend=daily_stats_list,
        team_distribution=team_stats_list,
    )


# --- 9. ATTENDANCE LOG (NEW) - admin dashboard: who/when/where/what-device ---
def get_attendance_log(db: Session, limit: int = 200) -> list[schemas.AttendanceLogRow]:
    rows = (
        db.query(models.Attendance, models.Volunteer)
        .join(models.Volunteer, models.Attendance.volunteer_id == models.Volunteer.volunteer_id)
        .order_by(models.Attendance.date.desc(), models.Attendance.check_in_time.desc())
        .limit(limit)
        .all()
    )

    log = []
    for attendance, volunteer in rows:
        ip_mismatch = bool(
            attendance.check_in_ip
            and attendance.check_out_ip
            and attendance.check_in_ip != attendance.check_out_ip
        )
        log.append(schemas.AttendanceLogRow(
            id=attendance.id,
            volunteer_id=attendance.volunteer_id,
            full_name=volunteer.full_name,
            team=volunteer.team,
            date=attendance.date,
            check_in_time=attendance.check_in_time,
            check_in_ip=attendance.check_in_ip,
            check_in_device=attendance.check_in_device,
            check_out_time=attendance.check_out_time,
            check_out_ip=attendance.check_out_ip,
            check_out_device=attendance.check_out_device,
            ip_mismatch=ip_mismatch,
        ))
    return log
