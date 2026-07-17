import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from .database import Base

# የአድሚን ሰንጠረዥ (Admin Table) - ሲስተሙን ለመቆጣጠር
class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


# የቮለንቲየር ሰንጠረዥ
class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, unique=True, index=True, nullable=False) # ለምሳሌ፡ ER-001
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    team = Column(String, nullable=False) # ለምሳሌ፡ Reading and literacy
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # ሰርተፍኬት ለመስጠት ብቁ መሆኑን መቆጣጠሪያ
    is_eligible_for_certificate = Column(Boolean, default=False)

    # ከ Attendance ጋር ያለው ግንኙነት (አድሚን ቮለንቲየር ሲሰርዝ የሱ አቴንዳንስ አብሮ እንዲሰረዝ)
    attendances = relationship("Attendance", back_populates="volunteer", cascade="all, delete-orphan")


# የክትትል ሰንጠረዥ (Attendance)
class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, ForeignKey("volunteers.volunteer_id"), nullable=False)
    
    # ቀን (YYYY-MM-DD)
    date = Column(String, default=lambda: datetime.date.today().isoformat(), nullable=False)
    
    # የሳምንት ቁጥር (Week 1, Week 2...)
    week_number = Column(Integer, nullable=False, default=1)
    ip_address = Column(String, nullable=True)
    device_info = Column(String, nullable=True)
    # ሰዓት ይመዘገባል (ከዚህ በመነሳት ሰዓት መቁጠር ይቻላል)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    
    status = Column(String, default="Present") # Present, Late, Absent

    volunteer = relationship("Volunteer", back_populates="attendances")