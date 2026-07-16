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
# ቮለንቲየር ለመመዝገብ (ለ Admin)
class VolunteerCreate(BaseModel):
    # volunteer_id በባክኤንድ በራስ-ሰር ስለሚመነጭ Optional ሆኗል
    volunteer_id: Optional[str] = Field(None, example="ER-001")
    full_name: str
    phone_number: Optional[str] = None
    # Team dropdown ሳይሆን input ስለሚሆን ባዶ ቢተውትም እንዳይበላሽ Optional ሆኗል
    team: Optional[str] = "General" 

# ቮለንቲየር መረጃ ለመመለስ (Response)
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
# ለአቴንዳንስ ጥያቄ (Check-in/Check-out)
class AttendanceRequest(BaseModel):
    volunteer_id: str
    user_lat: float
    user_lon: float
    action: str  # "check-in" ወይም "check-out"

# ለአቴንዳንስ ምላሽ (Response)
class AttendanceResponse(BaseModel):
    id: int
    volunteer_id: str
    date: str  # ቅርጸቱ፡ YYYY-MM-DD
    week_number: int
    check_in_time: Optional[datetime]
    check_out_time: Optional[datetime]
    status: str

    class Config:
        from_attributes = True


# ==================== 4. ANALYTICS / DASHBOARD SCHEMAS ====================
# ለአድሚን ዳሽቦርድ ውብ ቻርቶች መረጃዎችን ማደራጃ
class DailyStats(BaseModel):
    date: str
    present_count: int

class TeamStats(BaseModel):
    team_name: str
    count: int

class DashboardAnalytics(BaseModel):
    total_volunteers: int
    active_today: int
    # ለዳሽቦርድ የሚጠቅመውን ዛሬ የተገኘበትን ቁጥር ለመያዝ
    today_attendance_count: Optional[int] = 0 
    certified_volunteers_count: Optional[int] = 0
    daily_attendance_trend: List[DailyStats]
    team_distribution: List[TeamStats]