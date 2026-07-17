from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

# ==================== 1. ADMIN SCHEMAS ====================
class AdminLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None


# ==================== 2. VOLUNTEER SCHEMAS ====================
# አድሚን ቮለንቲየር ሲመዘግብ የሚጠየቀው መረጃ
class VolunteerCreate(BaseModel):
    full_name: str
    phone_number: Optional[str] = None
    team: Optional[str] = "General" 

class VolunteerResponse(BaseModel):
    id: int
    volunteer_id: str
    full_name: str
    phone_number: Optional[str]
    team: str
    registered_at: datetime
    is_eligible_for_certificate: bool

    class Config:
        from_attributes = True


# ==================== 3. ATTENDANCE SCHEMAS ====================
# Check-in/Check-out ሲደረግ የሚላክ መረጃ
class AttendanceRequest(BaseModel):
    volunteer_id: str
    user_lat: float
    user_lon: float
    action: str  # "check-in" ወይም "check-out"

# አቴንዳንስ መረጃ ሲመለስ
class AttendanceResponse(BaseModel):
    id: int
    volunteer_id: str
    date: str 
    week_number: int
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== 4. ANALYTICS / DASHBOARD SCHEMAS ====================
class DailyStats(BaseModel):
    date: str
    present_count: int

class TeamStats(BaseModel):
    team_name: str
    count: int

# schemas.py ውስጥ እንዲህ አድርገህ አስተካክለው
class DashboardAnalytics(BaseModel):
    total_volunteers: int
    today_checkins: int # እነዚህን መጠቀሙን አረጋግጥ
    today_checkouts: int
    certified_volunteers_count: int
    daily_attendance_trend: List[DailyStats]
    team_distribution: List[TeamStats]