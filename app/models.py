from datetime import datetime, timezone
import re
from sqlalchemy import create_engine, String, Text, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings
from contextvars import ContextVar

research_owner = ContextVar('research_owner', default='local')

class Base(DeclarativeBase):
    pass

class TelegramDelivery(Base):
    __tablename__ = 'telegram_deliveries'
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class ResearchAudit(Base):
    __tablename__ = 'research_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    source: Mapped[str] = mapped_column(String(150))
    payload: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(String(128), default='local', index=True)

class IPOAlertSubscriber(Base):
    __tablename__ = 'ipo_alert_subscribers'
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(20), default='telegram') # telegram or whatsapp
    target_id: Mapped[str] = mapped_column(String(128), index=True) # chat_id or phone
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_gmp: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_listings: Mapped[bool] = mapped_column(Boolean, default=True)

class MorningBriefingCache(Base):
    __tablename__ = 'morning_briefing_cache'
    id: Mapped[int] = mapped_column(primary_key=True)
    date_key: Mapped[str] = mapped_column(String(20), unique=True, index=True) # YYYY-MM-DD
    headline: Mapped[str] = mapped_column(String(255))
    script: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

db_url = settings.database_url
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)

if db_url.startswith('sqlite'):
    engine = create_engine(db_url, connect_args={'check_same_thread': False})
else:
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)

Session = sessionmaker(engine)

def save_research(symbol: str, source: str, payload: str):
    with Session.begin() as db:
        db.add(ResearchAudit(symbol=symbol, source=source, payload=payload, user_id=research_owner.get()))
