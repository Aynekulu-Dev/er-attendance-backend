import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from .database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, unique=True, index=True, nullable=False)  # ለምሳሌ፡ ER-001
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    team = Column(String, nullable=False)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)

    is_eligible_for_certificate = Column(Boolean, default=False)

    attendances = relationship("Attendance", back_populates="volunteer", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(String, ForeignKey("volunteers.volunteer_id"), nullable=False)

    date = Column(String, default=lambda: datetime.date.today().isoformat(), nullable=False)
    week_number = Column(Integer, nullable=False, default=1)

    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)

    # --- NEW: anti-fraud metadata (admin review only, does NOT auto-block) ---
    # ማን በምን IP/ስልክ check-in እንዳደረገ ለክትትል፣ ማጭበርበርን ("የጓደኛ ID መጠቀም") ለመለየት ይረዳል።
    check_in_ip = Column(String, nullable=True)
    check_in_device = Column(String, nullable=True)  # User-Agent string (phone/browser info)

    check_out_ip = Column(String, nullable=True)
    check_out_device = Column(String, nullable=True)

    status = Column(String, default="Present")  # Present, Late, Absent

    volunteer = relationship("Volunteer", back_populates="attendances")

    # NEW: race-condition guard. App-level logic (crud.record_attendance)
    # already blocks a 2nd check-in while a session is still open, but two
    # near-simultaneous requests (double-tap, retry) could both pass that
    # check before either commits. This partial unique index makes the
    # database itself refuse a second *open* (check_out_time IS NULL) row
    # for the same volunteer + date, closing that race window. It only
    # applies to Postgres/SQLite (both support partial indexes); on other
    # backends it's simply not created and app-level logic still applies.
    __table_args__ = (
        Index(
            "ix_one_open_session_per_volunteer_per_day",
            "volunteer_id",
            "date",
            unique=True,
            postgresql_where=(check_out_time.is_(None)),
            sqlite_where=(check_out_time.is_(None)),
        ),
    )