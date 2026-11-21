from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings
from contextvars import ContextVar

research_owner = ContextVar('research_owner', default='local')

class Base(DeclarativeBase):
    pass

class ResearchAudit(Base):
    __tablename__ = 'research_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    source: Mapped[str] = mapped_column(String(150))
    payload: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(String(128), default='local', index=True)

engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
Session = sessionmaker(engine)

def save_research(symbol: str, source: str, payload: str):
    with Session.begin() as db:
        db.add(ResearchAudit(symbol=symbol, source=source, payload=payload, user_id=research_owner.get()))
