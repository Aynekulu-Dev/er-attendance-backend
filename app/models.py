import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from .database import Base

# 1. አዲስ የጨመርነው የአድሚን ሰንጠረዥ (Admin Table)
class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


# 2. የቮለንቲየር ሰንጠረዥ (የተሻሻለው)
class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, unique=True, index=True, nullable=False) # ለምሳሌ ER-001
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    team = Column(String, nullable=False) # ለምሳሌ Reading and literacy
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # የሰመር ካምፕ ሲያልቅ ሰርተፍኬት ለመስጠት ብቁ መሆኑን መቆጣጠሪያ
    is_eligible_for_certificate = Column(Boolean, default=False)

    # ከ Attendance ጋር ያለው ግንኙነት (አድሚኑ ቮለንቲየር ሲያጠፋ የሱ አቴንዳንስ አብሮ እንዲጠፋ cascade ተጨምሯል)
    attendances = relationship("Attendance", back_populates="volunteer", cascade="all, delete-orphan")


# 3. የመገኘት ሰንጠረዥ (የተሻሻለው)
class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, ForeignKey("volunteers.volunteer_id"), nullable=False)
    
    # እዚህ ጋር Date ዴታ ታይፑን ወደ String መቀየር ወደፊት ሪፖርት ለመስራት እና ዳታቤዝ ላይ ኩዌሪ ለማድረግ በጣም ያቀላል
    date = Column(String, default=lambda: datetime.date.today().isoformat(), nullable=False) # ፎርማት፡ YYYY-MM-DD
    
    # ቮለንቲየሩ የገባበትን የሰመር ካምፕ ሳምንት (Week 1, Week 2, ... Week 7) ለመለየት
    week_number = Column(Integer, nullable=False, default=1)
    
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    
    status = Column(String, default="Present") # Present, Late, Absent ወዘተ

    volunteer = relationship("Volunteer", back_populates="attendances")