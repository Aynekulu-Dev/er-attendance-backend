from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

# ==================== 1. GENERAL RESPONSE (User-Friendly) ====================
class GenericResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

# ==================== 2. ADMIN SCHEMAS ====================
class AdminLogin(BaseModel):
    username: str = Field(..., example="admin")
    password: str = Field(..., example="secret123")

class Token(BaseModel):
    access_token: str
    token_type: str

# ==================== 3. VOLUNTEER SCHEMAS ====================
class VolunteerCreate(BaseModel):
    full_name: str
    phone_number: Optional[str] = None
    team: str = "General" 

class VolunteerResponse(BaseModel):
    volunteer_id: str
    full_name: str
    team: str
    # አድሚኑ ሲመዘግብ የሚመለሰው መረጃ
    message: str = "Volunteer registered successfully!"

    class Config:
        from_attributes = True

# ==================== 4. ATTENDANCE SCHEMAS ====================
class AttendanceRequest(BaseModel):
    volunteer_id: str = Field(..., description="የቮለንቲየሩ ልዩ መታወቂያ (e.g., ER-001)")
    user_lat: float
    user_lon: float
    action: str = Field(..., description="'check-in' ወይም 'check-out' ብቻ")

class AttendanceStatus(BaseModel):
    success: bool
    action: str
    timestamp: datetime
    volunteer_name: str
    message: str  # ለምሳሌ፡ "Check-in successful! Welcome back."

# ==================== 5. DASHBOARD / ANALYTICS SCHEMAS ====================
class DailyStats(BaseModel):
    date: str
    present_count: int

class TeamStats(BaseModel):
    team_name: str
    count: int

class DashboardAnalytics(BaseModel):
    total_volunteers: int
    today_checkins: int
    today_checkouts: int
    active_now: int  # በስራ ላይ ያሉ
    daily_attendance_trend: List[DailyStats]
    team_distribution: List[TeamStats]