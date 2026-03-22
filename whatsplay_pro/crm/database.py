from sqlalchemy import create_all, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from whatsplay_pro.core.config import Config

Base = declarative_base()

class Contact(Base):
    """SQLite-backed CRM contact model."""
    __tablename__ = 'contacts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    tags = Column(String(255), nullable=True) # JSON or Comma separated
    notes = Column(Text, nullable=True)
    is_blacklisted = Column(Boolean, default=False)
    last_interaction = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    messages = relationship("Message", back_populates="contact")

class Message(Base):
    """SQLite message log storage."""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True)
    chat_id = Column(String(50), index=True) # @c.us or @g.us
    content = Column(Text, nullable=False)
    is_incoming = Column(Boolean, default=True)
    media_path = Column(String(255), nullable=True)
    status = Column(String(20), default="sent") # sent, delivered, read, failed
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    contact = relationship("Contact", back_populates="messages")

class Campaign(Base):
    """Bulk messaging campaign storage."""
    __tablename__ = 'campaigns'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    template = Column(Text, nullable=False)
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(String(20), default="pending") # pending, running, completed, paused
    scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database Engine & Session setup
from sqlalchemy import create_engine
engine = create_engine(f"sqlite:///{Config.DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables in the SQLite database."""
    Base.metadata.create_all(bind=engine)
