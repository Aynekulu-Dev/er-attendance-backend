import os
import csv
from datetime import datetime, date, timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import models, schemas
import math

# --- 1. GEOFENCING CONSTANTS ---
COMPANY_LAT = float(os.getenv("COMPANY_LAT", "9.012345"))
COMPANY_LON = float(os.getenv("COMPANY_LON", "38.754321"))
ALLOWED_RADIUS_METERS = float(os.getenv("ALLOWED_RADIUS_METERS", "5000"))

# NEW: በቀን ስንት ዙር (check-in→check-out cycle) እንደሚፈቀድ - ለምሳሌ ጠዋት 1 ዙር +
# ከሰዓት 1 ዙር = 2. ከዚህ በላይ ማድረግ ካስፈለገ .env ውስጥ MAX_DAILY_SESSIONS ቀይር።
MAX_DAILY_SESSIONS = int(os.getenv("MAX_DAILY_SESSIONS", "2"))

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


# --- 2b. SHARED-DEVICE SOFT-FLAG WINDOW ---
# ተመሳሳይ ስልክ (IP+device) ለ2 የተለያዩ Volunteer ID በቀኑ ውስጥ ጥቅም ላይ ቢውልም፣ በሰዓት ልዩነት
# (ለምሳሌ ጠዋትና ማታ) ከሆነ ብዙም አያሳስብም - አንድ ቤተሰብ ስልክ እየተጋሩ ሊሆን ይችላል። ስለዚህ flag
# የሚደረገው ሁለቱ check-in በዚህ የደቂቃ ልዩነት ውስጥ ብቻ ሲፈጸሙ ነው (በአካል እጅ ለእጅ የተላለፈ ስልክ
# የሚያመለክት ስለሆነ)። ይህ ቁጥር ማስተካከል ቢያስፈልግ ከዚህ ብቻ ይቀየራል።
SHARED_DEVICE_WINDOW_MINUTES = int(os.getenv("SHARED_DEVICE_WINDOW_MINUTES", "10"))


def _compute_shared_device_flags(records) -> set:
    """
    records: የ Attendance objects ዝርዝር (check_in_ip, check_in_device, check_in_time,
    volunteer_id, date ሊኖራቸው ይገባል)።

    ይመልሳል፡ በተመሳሳይ ቀን፣ ተመሳሳይ (IP, device) ግን ለተለያዩ Volunteer ID፣ በ
    SHARED_DEVICE_WINDOW_MINUTES ውስጥ check-in የተደረገባቸው attendance.id ዎች ስብስብ።

    Soft-flag ብቻ ነው - ምንም አይከለክልም፣ admin ብቻ ለክትትል ይጠቀምበታል።
    """
    groups: dict[tuple, list] = {}
    for r in records:
        if r.check_in_ip and r.check_in_device and r.check_in_time:
            key = (r.date, r.check_in_ip, r.check_in_device)
            groups.setdefault(key, []).append(r)

    window = timedelta(minutes=SHARED_DEVICE_WINDOW_MINUTES)
    flagged_ids: set = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.volunteer_id == b.volunteer_id:
                    continue  # ተመሳሳይ ሰው ብቻ ነው - ችግር የለውም
                if abs(a.check_in_time - b.check_in_time) <= window:
                    flagged_ids.add(a.id)
                    flagged_ids.add(b.id)
    return flagged_ids


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

    # NEW: ከ MAX_DAILY_SESSIONS ጋር በቀን ከ1 በላይ record ሊኖር ስለሚችል፣ "የተገኘበት ቀን"
    # ለ certificate ብቁነት በ record ብዛት ሳይሆን በ *distinct ቀን* (date) መቆጠር አለበት -
    # አለበለዚያ አንድ ሰው በ1 ቀን 2 ዙር ሰርቶ እንደ 2 ቀን ተቆጥሮ ብቁነቱን ያጭበረብራል።
    weekly_days_present = {week: set() for week in range(1, 8)}
    for record in attendances:
        if record.week_number in weekly_days_present:
            weekly_days_present[record.week_number].add(record.date)

    is_eligible = True
    for week, days in weekly_days_present.items():
        if len(days) < 3:
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


# NEW: admin dashboard "edit volunteer" - only touches fields the admin
# actually sent (Pydantic's exclude_unset), so a partial edit (e.g. just
# fixing a typo in the team name) doesn't accidentally wipe out other fields.
def update_volunteer(db: Session, volunteer_id: str, update: schemas.VolunteerUpdate):
    volunteer = get_volunteer_by_id(db, volunteer_id)
    if not volunteer:
        return None

    changes = update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(volunteer, field, value)

    db.commit()
    db.refresh(volunteer)
    return volunteer


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
            "message": f"«{request.volunteer_id}» የሚባል መታወቂያ አላገኘንም። በትክክል መፃፍህን አረጋግጥ (ለምሳሌ፡ ER-001)፣ ወይም ገና ካልተመዘገብክ አድሚን አነጋግር።",
            "data": None,
        }

    distance = calculate_distance(request.user_lat, request.user_lon, COMPANY_LAT, COMPANY_LON)
    if distance > ALLOWED_RADIUS_METERS:
        return {
            "status": "error",
            "message": f"ካምፑ አካባቢ አይደለህም (አሁን ካለህበት {int(distance)} ሜትር ይርቃል)። ወደ ካምፑ ግቢ ገብተህ እንደገና ሞክር።",
            "data": None,
        }

    today_str = date.today().isoformat()
    current_week = get_current_week_number(db)

    # NEW: ከ1 ይልቅ ዛሬ ያሉትን ሁሉንም records እናመጣለን (እስከ MAX_DAILY_SESSIONS ድረስ
    # ብዙ ዙር (check-in→check-out cycle) እንዲኖር ስለምንፈቅድ - ለምሳሌ ጠዋት 1 ዙር +
    # ከሰዓት 1 ዙር)። "ክፍት" ዙር ማለት check-in ያለው ግን check-out የሌለው ነው።
    todays_records = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.volunteer_id == request.volunteer_id,
            models.Attendance.date == today_str,
        )
        .order_by(models.Attendance.check_in_time.asc())
        .all()
    )
    open_record = next((r for r in todays_records if r.check_out_time is None), None)
    sessions_used = len(todays_records)

    if request.action == "check-in":
        if open_record:
            return {
                "status": "error",
                "message": (
                    f"{volunteer.full_name}፣ አሁን ባለህበት ክፍለ ጊዜ ላይ ነህ (check-out ገና አላደረግህም)። "
                    "መጀመሪያ 'Check out' ተጫን፣ ከዚያ አዲስ ዙር መጀመር ትችላለህ።"
                ),
                "data": schemas.AttendanceResponse.model_validate(open_record),
            }
        if sessions_used >= MAX_DAILY_SESSIONS:
            return {
                "status": "error",
                "message": (
                    f"{volunteer.full_name}፣ ዛሬ የተፈቀደውን ከፍተኛ ልክ ({MAX_DAILY_SESSIONS} ዙር) "
                    "ደርሰሃል - ለዛሬ ተጨማሪ check-in ማድረግ አትችልም።"
                ),
                "data": None,
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
        try:
            db.commit()
        except IntegrityError:
            # ሁለት check-in ጥያቄዎች በአንድ ጊዜ (double-tap/network retry) ሲላኩ
            # ከላይ ያለው ፍተሻ ሁለቱንም ቢያሳልፍም፣ DB partial unique index (models.py)
            # ሁለተኛውን ይከለክለዋል - እዚህ በጸጋ ይያዘዋል፣ raw 500 error ከመስጠት ይልቅ።
            db.rollback()
            return {
                "status": "error",
                "message": (
                    f"{volunteer.full_name}፣ Check-in ልክ አሁን ተመዝግቧል (ምናልባት ደጋግመህ ተጭነህ ይሆናል) - "
                    "ገጹን አድሶ ሁኔታውን አረጋግጥ።"
                ),
                "data": None,
            }
        db.refresh(attendance_record)
        session_no = sessions_used + 1
        friendly_message = (
            f"እንኳን ደህና መጣህ፣ {volunteer.full_name}! Check-in ተመዝግቧል (ዙር {session_no}/{MAX_DAILY_SESSIONS})።"
        )

    elif request.action == "check-out":
        if not open_record:
            if sessions_used >= MAX_DAILY_SESSIONS:
                message = (
                    f"{volunteer.full_name}፣ ዛሬ ያሉህን ሁሉንም ዙር ({MAX_DAILY_SESSIONS}) "
                    "ጨርሰሃል - ክፍት ዙር የለም።"
                )
            elif sessions_used == 0:
                message = f"{volunteer.full_name}፣ ገና Check-in አላደረግህም - መጀመሪያ 'Check in' ተጫን።"
            else:
                message = (
                    f"{volunteer.full_name}፣ አሁን ክፍት ዙር የለህም (ያለፈውን ዙር check-out አድርገሃል)። "
                    "አዲስ ዙር መጀመር ከፈለግህ መጀመሪያ 'Check in' ተጫን።"
                )
            return {"status": "error", "message": message, "data": None}

        attendance_record = open_record
        attendance_record.check_out_time = datetime.utcnow()
        attendance_record.check_out_ip = ip_address
        attendance_record.check_out_device = device_info
        db.commit()
        db.refresh(attendance_record)
        friendly_message = f"ደህና ሰንብት፣ {volunteer.full_name}! Check-out ተመዝግቧል፣ ጥሩ ስራ!"

    else:
        return {
            "status": "error",
            "message": "ያልታወቀ ትዕዛዝ ተልኳል። ገጹን አድሶ (refresh) እንደገና ሞክር፣ ችግር ከቀጠለ አድሚን አነጋግር።",
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

    # --- Soft-flag count for today's stat card: how many of today's check-ins
    # share a (IP, device) pair with a DIFFERENT volunteer's check-in within
    # SHARED_DEVICE_WINDOW_MINUTES of each other. Informational only.
    todays_checkins = db.query(models.Attendance).filter(
        models.Attendance.date == today_str,
        models.Attendance.check_in_ip.isnot(None),
        models.Attendance.check_in_device.isnot(None),
    ).all()

    suspicious_checkins_today = len(_compute_shared_device_flags(todays_checkins))

    return schemas.DashboardAnalytics(
        total_volunteers=total_volunteers,
        today_checkins=today_checkins,
        today_checkouts=today_checkouts,
        certified_volunteers_count=certified_volunteers_count,
        daily_attendance_trend=daily_stats_list,
        team_distribution=team_stats_list,
        suspicious_checkins_today=suspicious_checkins_today,
    )


# --- 8b. LIVE CSV EXPORT (generated from DB on every request, not from the
# on-disk backup file) ---
# ለምን፡ `append_to_csv_backup` የሚጽፈው ፋይል Render (እና ሌሎች cloud host) ላይ
# ephemeral disk ላይ ስለሆነ redeploy/restart ሲደረግ ሊጠፋ ይችላል - ያኔ export
# endpoint ቀድሞ ያንን ፋይል ብቻ ስለሚያገለግል 404 ይመልስ ነበር (ምንም ባይጠፋም እንኳ ፋይሉ
# ማንኛውንም date range/team ማጣራት አይችልም ነበር)። ስለዚህ export ራሱ ሁልጊዜ ከ DB
# ቀጥታ ይመነጫል - ፋይሉ ቢጠፋ/ባይኖርም ችግር የለውም፣ ትክክለኛው ምንጭ DB ብቻ ነው።
def generate_attendance_csv(db: Session) -> str:
    import io

    rows = (
        db.query(models.Attendance, models.Volunteer)
        .join(models.Volunteer, models.Attendance.volunteer_id == models.Volunteer.volunteer_id)
        .order_by(models.Attendance.date.asc(), models.Attendance.check_in_time.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Attendance_ID", "Volunteer_ID", "Full_Name", "Team",
        "Date", "Week_Number", "Check_In_Time", "Check_In_IP", "Check_In_Device",
        "Check_Out_Time", "Check_Out_IP", "Check_Out_Device", "Status"
    ])

    for attendance, volunteer in rows:
        writer.writerow([
            attendance.id,
            attendance.volunteer_id,
            volunteer.full_name,
            volunteer.team,
            attendance.date,
            attendance.week_number,
            attendance.check_in_time.isoformat() if attendance.check_in_time else "",
            attendance.check_in_ip or "",
            attendance.check_in_device or "",
            attendance.check_out_time.isoformat() if attendance.check_out_time else "",
            attendance.check_out_ip or "",
            attendance.check_out_device or "",
            attendance.status,
        ])

    return output.getvalue()


# --- 9. ATTENDANCE LOG (NEW) - admin dashboard: who/when/where/what-device ---
def get_attendance_log(db: Session, limit: int = 200) -> list[schemas.AttendanceLogRow]:
    rows = (
        db.query(models.Attendance, models.Volunteer)
        .join(models.Volunteer, models.Attendance.volunteer_id == models.Volunteer.volunteer_id)
        .order_by(models.Attendance.date.desc(), models.Attendance.check_in_time.desc())
        .limit(limit)
        .all()
    )

    # --- Soft-flag: same (date, check-in IP, check-in device) used for check-in by
    # a DIFFERENT volunteer_id within SHARED_DEVICE_WINDOW_MINUTES of each other.
    # This never blocks a check-in - it only surfaces a badge for the admin to
    # review, since e.g. two siblings sharing one phone hours apart would
    # otherwise look identical to "used a friend's ID right at the door".
    flagged_ids = _compute_shared_device_flags([attendance for attendance, _ in rows])

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
            shared_device_flag=attendance.id in flagged_ids,
        ))
    return log