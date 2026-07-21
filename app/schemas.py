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


# NEW: admin dashboard "edit volunteer" - all fields optional so the admin
# can change just one thing (e.g. only the team) without resending everything.
# volunteer_id is intentionally NOT editable here - it's the primary lookup
# key (used as a foreign key on every Attendance row), so changing it would
# either need a cascading rename or break existing attendance history.
class VolunteerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    team: Optional[str] = None

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
    # NOTE: ip_address/device_info ከ client በፍጹም አንቀበልም - client ላይ ማጭበርበር
    # ይቻላልና በ FastAPI backend በራሱ ከ Request object ላይ እንወስዳለን (main.py ይመልከቱ)።

class AttendanceResponse(BaseModel):
    id: int
    volunteer_id: str
    date: str
    week_number: int
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    check_in_ip: Optional[str] = None
    check_in_device: Optional[str] = None
    check_out_ip: Optional[str] = None
    check_out_device: Optional[str] = None
    status: str

    class Config:
        from_attributes = True


class AttendanceActionResponse(BaseModel):
    status: str  # "success" or "error"
    message: str
    data: Optional[AttendanceResponse] = None


# NEW: admin-facing attendance log row (attendance + volunteer name/team combined)
# so the dashboard can show "who, when, from where, on what device" in one table.
class AttendanceLogRow(BaseModel):
    id: int
    volunteer_id: str
    full_name: str
    team: str
    date: str
    check_in_time: Optional[datetime] = None
    check_in_ip: Optional[str] = None
    check_in_device: Optional[str] = None
    check_out_time: Optional[datetime] = None
    check_out_ip: Optional[str] = None
    check_out_device: Optional[str] = None
    ip_mismatch: bool  # check-in IP != check-out IP -> flag for admin review only

    # NEW: same (date, IP, device) used to check in for a DIFFERENT volunteer_id
    # that same day -> soft-flag only, admin reviews, nothing is auto-blocked
    # (e.g. siblings legitimately sharing one phone would otherwise look like fraud).
    shared_device_flag: bool = False


# ==================== 4. ANALYTICS / DASHBOARD SCHEMAS ====================
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
    certified_volunteers_count: int
    daily_attendance_trend: List[DailyStats]
    team_distribution: List[TeamStats]
    suspicious_checkins_today: int = 0