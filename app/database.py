import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# .env ፋይል ውስጥ ያሉትን ተለዋዋጮች ለመጫን
load_dotenv()

# ከ .env ላይ የዳታቤዝ URL ን መውሰድ (ከሌለ ወደ SQLite fallback ያደርጋል)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./attendance.db")

# ለአንዳንድ ክላውድ ሰርቨሮች (ለምሳሌ Render) 'postgres://' የሚለውን ወደ 'postgresql://' መቀየር
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# PostgreSQL ከሆነ ከ SQLite የተለየ configuration ይፈልጋል
if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    # pool_pre_ping=True ግንኙነቱ ቢቋረጥ እንኳ በራሱ እንዲቀጥል ያደርጋል
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
else:
    # SQLite ከሆነ የ thread ጥበቃውን እናጠፋዋለን
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# የዳታቤዝ ሴሽን ለኤፒአዮች ለማቅረብ (Dependency)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()