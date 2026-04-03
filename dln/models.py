# dln/models.py

import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ExperimentSession(Base):
    __tablename__ = 'ExperimentSession'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    start_time = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    context_json = Column(JSON, nullable=False)
    final_summary = Column(Text, nullable=True)
    final_hash = Column(String, nullable=True)
    status = Column(String, default='active', nullable=False)  # 'active', 'finalized'

    science_logs = relationship("ScienceLog", back_populates="session")
    transaction_logs = relationship("TransactionLog", back_populates="session")

class ScienceLog(Base):
    __tablename__ = 'ScienceLog'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('ExperimentSession.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    entry_type = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    supersedes_id = Column(Integer, ForeignKey('ScienceLog.id'), nullable=True)
    correction_reason = Column(Text, nullable=True)

    session = relationship("ExperimentSession", back_populates="science_logs")

class TransactionLog(Base):
    __tablename__ = 'TransactionLog'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('ExperimentSession.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    raw_io = Column(Text, nullable=False)

    session = relationship("ExperimentSession", back_populates="transaction_logs")

class Protocol(Base):
    __tablename__ = 'Protocol'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # FIXED: Replaced ForeignKeyConstraint with UniqueConstraint
    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_protocol_name_version'),
    )