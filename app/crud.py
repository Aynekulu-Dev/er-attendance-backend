import os
import csv
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from . import models, schemas
import math

# --- 1. GEOFENCING CONSTANTS (ከ .env ወይም default እሴቶች መውሰድ) ---
# ለሙከራ ያህል ርቀቱ እንዲፈቅድልህ ALLOWED_RADIUS_METERS በዲፎልት 5000 ሜትር (5 ኪ.ሜ) ተደርጓል።
# ይህንን ከፈለግህ በ .env ፋይልህ ላይ ALLOWED_RADIUS_METERS=100 በማድረግ መቆጣጠር ትችላለህ።
COMPANY_LAT = float(os.getenv("COMPANY_LAT", "9.012345"))
COMPANY_LON = float(os.getenv("COMPANY_LON", "38.754321"))
ALLOWED_RADIUS_METERS = float(os.getenv("ALLOWED_RADIUS_METERS", "5000")) # በሜትር

# --- 2. ራስ-ሰር የ CSV BACKUP ፎልደር ማዘጋጃ ---
BACKUP_DIR = "backups"
BACKUP_FILE = os.path.join(BACKUP_DIR, "attendance_backup.csv")

def append_to_csv_backup(attendance_record: models.Attendance, volunteer_name: str, team: str):
    """
    አዲስ የ Attendance መረጃ በገባ ቁጥር በራስ-ሰር ወደ backups/attendance_backup.csv የሚጨምር ተግባር (Append-only)
    """
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            
        file_exists = os.path.exists(BACKUP_FILE)
        
        with open(BACKUP_FILE, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            # ፋይሉ አዲስ ከሆነ ራስጌ (Header) እንጽፋለን
            if not file_exists:
                writer.writerow([
                    "Backup_Timestamp", "Attendance_ID", "Volunteer_ID", "Full_Name", "Team", 
                    "Date", "Week_Number", "Check_In_Time", "Check_Out_Time", "Status"
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
                attendance_record.check_out_time.isoformat() if attendance_record.check_out_time else "",
                attendance_record.status
            ])
    except Exception as e:
        print(f"Error writing to CSV backup: {e}")

# --- 3. የርቀት ማስያ ሎጂክ (Haversine Formula) ---
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    በሁለት የጂፒኤስ መጋጠሚያዎች (GPS coordinates) መካከል ያለውን ርቀት በሜትር ያሰላል።
    """
    R = 6371000  # የምድር ራዲየስ በሜትር
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- 4. የ 7 ሳምንት ሰርተፍኬት ብቁነት መፈተሻ ሎጂክ ---
def update_certificate_eligibility(db: Session, volunteer_id: str):
    """
    አንድ ቮለንቲየር በየሳምንቱ ቢያንስ 3 ቀን (በጠቅላላው ከ7ቱ ሳምንት ውስጥ ቢያንስ 21 ቀናት) 
    ተገኝቶ ከሆነ ለሰርተፍኬት ብቁ (is_eligible_for_certificate = True) ያደርገዋል።
    """
    # ሁሉንም የዚህ ቮለንቲየር መገኘት መረጃዎች እናመጣለን
    attendances = db.query(models.Attendance).filter(
        models.Attendance.volunteer_id == volunteer_id,
        models.Attendance.status == "Present"
    ).all()
    
    # በየሳምንቱ (ከ 1 እስከ 7) የተገኘባቸውን ቀናት እንቆጥራለን
    weekly_presence = {week: 0 for week in range(1, 8)}
    for record in attendances:
        if record.week_number in weekly_presence:
            weekly_presence[record.week_number] += 1
            
    # በየሳምንቱ ቢያንስ 3 ቀን መገኘቱን እንፈትሻለን (ለ 7ቱም ሳምንታት)
    is_eligible = True
    for week, count in weekly_presence.items():
        if count < 3: # በሳምንቱ ውስጥ ከ 3 ቀን በታች ከተገኘ ብቁ አይደለም
            is_eligible = False
            break
            
    # የቮለንቲየሩን መረጃ አዘምን
    volunteer = db.query(models.Volunteer).filter(models.Volunteer.volunteer_id == volunteer_id).first()
    if volunteer:
        volunteer.is_eligible_for_certificate = is_eligible
        db.commit()
        db.refresh(volunteer)

# --- 5. የሰመር ካምፕ የሳምንት ቁጥር ማስያ ---
def get_current_week_number(db: Session) -> int:
    """
    የመጀመሪያው ቮለንቲየር ከተመዘገበበት ቀን ጀምሮ ያለውን ጊዜ በማስላት 
    አሁን ያለንበትን የሰመር ካምፕ ሳምንት (ከ 1 እስከ 7) ይወስናል።
    """
    first_volunteer = db.query(models.Volunteer).order_by(models.Volunteer.registered_at.asc()).first()
    if not first_volunteer:
        return 1 # እስካሁን ማንም ካልተመዘገበ ሳምንት 1 ላይ ነን
        
    start_date = first_volunteer.registered_at.date()
    today = date.today()
    days_passed = (today - start_date).days
    
    # ሳምንቱን ማስላት (ለምሳሌ ከ0-6 ቀን = Week 1, ከ7-13 ቀን = Week 2...)
    week_number = (days_passed // 7) + 1
    
    # ከ 7 ሳምንት በላይ እንዳይሄድ መገደብ
    return min(max(week_number, 1), 7)

# --- 6. VOLUNTEER CRUD ---
def create_volunteer(db: Session, volunteer: schemas.VolunteerCreate, new_id: str): # new_id ተቀባይ መሆን አለበት
    db_volunteer = models.Volunteer(
        volunteer_id=new_id, # በ main.py የመጣውን ID እዚህ ተጠቀም
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
def record_attendance(db: Session, request: schemas.AttendanceRequest):
    """
    Check-in ወይም Check-out ሲያደርጉ መረጃ መዝጋቢ።
    ርቀታቸውን በመለካት ከክልል ውጭ ከሆነ ውድቅ ያደርጋል፣ እንዲሁም በራስ-ሰር CSV ባክአፕ ይጽፋል።
    """
    # 1. ቮለንቲየሩ መኖሩን ማረጋገጥ
    volunteer = get_volunteer_by_id(db, request.volunteer_id)
    if not volunteer:
        return {"status": "error", "message": "ይህ የቮለንቲየር መታወቂያ (ID) አልተመዘገበም!"}

    # 2. የጂፒኤስ ርቀት መፈተሽ
    distance = calculate_distance(request.user_lat, request.user_lon, COMPANY_LAT, COMPANY_LON)
    if distance > ALLOWED_RADIUS_METERS:
        return {
            "status": "error", 
            "message": f"ከተፈቀደው የካምፕ ክልል ውጭ ነህ! ካለህበት ርቀት፡ {int(distance)} ሜትር (የተፈቀደው፡ {int(ALLOWED_RADIUS_METERS)} ሜትር)"
        }

    today_str = date.today().isoformat()
    current_week = get_current_week_number(db)

    # የዛሬውን የመገኘት መረጃ መፈለግ
    attendance_record = db.query(models.Attendance).filter(
        models.Attendance.volunteer_id == request.volunteer_id,
        models.Attendance.date == today_str
    ).first()

    if request.action == "check-in":
        if attendance_record:
            return {"status": "error", "message": "ዛሬ ቀድመህ Check-in አድርገሃል!"}
            
        attendance_record = models.Attendance(
            volunteer_id=request.volunteer_id,
            date=today_str,
            week_number=current_week,
            check_in_time=datetime.utcnow(),
            status="Present"
        )
        db.add(attendance_record)
        db.commit()
        db.refresh(attendance_record)

    elif request.action == "check-out":
        if not attendance_record:
            return {"status": "error", "message": "መጀመሪያ Check-in ማድረግ አለብህ!"}
        if attendance_record.check_out_time:
            return {"status": "error", "message": "ዛሬ ቀድመህ Check-out አድርገሃል!"}
            
        attendance_record.check_out_time = datetime.utcnow()
        db.commit()
        db.refresh(attendance_record)

    # 3. ለሰርተፍኬት ብቁነቱን በራስ-ሰር መፈተሽ እና ማዘመን
    update_certificate_eligibility(db, request.volunteer_id)

    # 4. መፍትሄ ሀ፦ አውቶማቲክ CSV Backup ማመንጨት (በየቀኑ/በየሰዓቱ አዲስ ዳታ ሲመጣ)
    append_to_csv_backup(attendance_record, volunteer.full_name, volunteer.team)

    return {"status": "success", "data": attendance_record}

# --- 8. DASHBOARD ANALYTICS ---
def get_dashboard_analytics(db: Session) -> schemas.DashboardAnalytics:
    total_volunteers = db.query(models.Volunteer).count()
    
    today_str = date.today().isoformat()
    active_today = db.query(models.Attendance).filter(
        models.Attendance.date == today_str
    ).count()
    
    eligible_for_certificate = db.query(models.Volunteer).filter(
        models.Volunteer.is_eligible_for_certificate == True
    ).count()
    
    # የዕለት ተዕለት የመገኘት ታሪክ (Trend)
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
    
    # የቡድኖች ስርጭት (Team Distribution)
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
        active_today=active_today,
        today_attendance_count=active_today,
        certified_volunteers_count=eligible_for_certificate,
        daily_attendance_trend=daily_stats_list,
        team_distribution=team_stats_list
    )