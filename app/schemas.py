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


# NEW: register endpoint's response wrapper - user friendly message + data
class VolunteerRegisterResponse(BaseModel):
    status: str = "success"
    message: str
    data: VolunteerResponse


# ==================== 3. ATTENDANCE SCHEMAS ====================
class AttendanceRequest(BaseModel):
    volunteer_id: str
    user_lat: float
    user_lon: float
    action: str  # "check-in" ወይም "check-out"

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


# NEW: check-in/check-out endpoint's response wrapper
# (data is Optional because error cases—e.g. "wrong location"—don't have a record)
class AttendanceActionResponse(BaseModel):
    status: str  # "success" or "error"
    message: str
    data: Optional[AttendanceResponse] = None


# ==================== 4. ANALYTICS / DASHBOARD SCHEMAS ====================
class DailyStats(BaseModel):
    date: str
    present_count: int

class TeamStats(BaseModel):
    team_name: str
    count: int

# NOTE: field names here MUST match exactly what crud.get_dashboard_analytics()
# constructs, otherwise you'll get a pydantic ValidationError.
class DashboardAnalytics(BaseModel):
    total_volunteers: int
    today_checkins: int
    today_checkouts: int
    certified_volunteers_count: int
    daily_attendance_trend: List[DailyStats]
    team_distribution: List[TeamStats]