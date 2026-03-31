# host/dln/storage_manager.py
import os
import json
import uuid
import csv
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, Column, String, DateTime, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

Base = declarative_base()

class SchemaInfo(Base):
    __tablename__ = 'schema_info'
    version = Column(Integer, primary_key=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class Experiment(Base):
    __tablename__ = 'experiments'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255))
    objective = Column(Text)
    summary = Column(Text) # Reflection summary of the whole session
    status = Column(String(50))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    world_model = Column(JSON) # Snapshot of lab state at start
    entries = relationship("Entry", back_populates="experiment", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="experiment", cascade="all, delete-orphan")

class Entry(Base):
    """
    Generic event ledger. 
    Types: INTENT (User Goal), PLAN (AI JSON), OBSERVATION (Hardware Response), REFLECTION (AI Summary)
    """
    __tablename__ = 'entries'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey('experiments.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String(50)) 
    content = Column(JSON)
    experiment = relationship("Experiment", back_populates="entries")
    attachments = relationship("Attachment", back_populates="entry", cascade="all, delete-orphan")

class Attachment(Base):
    """
    Hardware-agnostic data storage. 
    Use context_tags for IDs like 'well', 'electrode', 'vial_id', etc.
    """
    __tablename__ = 'attachments'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey('experiments.id'))
    entry_id = Column(String(36), ForeignKey('entries.id'), nullable=True)
    filename = Column(String(255))
    file_path = Column(String(512))
    data_type = Column(String(50))
    context_tags = Column(JSON) # Generic bucket for hardware-specific identifiers
    experiment = relationship("Experiment", back_populates="attachments")
    entry = relationship("Entry", back_populates="attachments")

class StorageManager:
    SCHEMA_VERSION = 3 

    def __init__(self, base_dir=".talos"):
        self.base_dir = Path(base_dir).resolve()
        self.db_path = self.base_dir / "lab_notebook.db"
        self.storage_path = self.base_dir / "data_storage"
        self._ensure_dirs()
        engine_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(engine_url)
        self.Session = sessionmaker(bind=self.engine)
        self._init_db()

    def _ensure_dirs(self):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        Base.metadata.create_all(self.engine)
        session = self.Session()
        try:
            v = session.query(SchemaInfo).first()
            if not v:
                session.add(SchemaInfo(version=self.SCHEMA_VERSION))
                session.commit()
            elif v.version < self.SCHEMA_VERSION:
                # Basic migration: logic could be expanded here
                v.version = self.SCHEMA_VERSION
                session.commit()
        finally:
            session.close()

    def create_experiment(self, title, objective=None, world_model=None):
        session = self.Session()
        try:
            exp = Experiment(title=title, objective=objective, status="running", world_model=world_model)
            session.add(exp)
            session.commit()
            exp_id = exp.id
            (self.storage_path / exp_id).mkdir(parents=True, exist_ok=True)
            return exp_id
        finally: session.close()

    def log_event(self, exp_id, event_type, content):
        """Logs a generic transaction event (INTENT, PLAN, OBSERVATION, REFLECTION)."""
        session = self.Session()
        try:
            entry = Entry(experiment_id=exp_id, event_type=event_type, content=content)
            session.add(entry)
            session.commit()
            return entry.id
        finally: session.close()

    def save_artifact(self, exp_id, entry_id, device, command, payload, tags=None):
        """
        Saves raw instrument data and registers it with context tags.
        Replaces the old Registry logic.
        """
        session = self.Session()
        try:
            # 1. File management
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            filename_base = f"{device}_{command}_{timestamp_str}_{unique_id}"
            exp_folder = self.storage_path / exp_id
            
            json_path = exp_folder / f"{filename_base}.json"
            with open(json_path, 'w') as f:
                json.dump(payload, f, indent=2)

            # 2. Metadata and Tags
            metadata = payload.get('metadata', {})
            # Ensure tags is a dictionary
            context_tags = tags if isinstance(tags, dict) else {}
            context_tags['device'] = device
            context_tags['command'] = command

            attachment = Attachment(
                experiment_id=exp_id, 
                entry_id=entry_id, 
                filename=f"{filename_base}.json",
                file_path=str(json_path), 
                data_type=metadata.get('data_type', 'unknown'),
                context_tags=context_tags
            )
            session.add(attachment)

            # 3. Best-effort CSV (for flat data)
            data_content = payload.get('data', {})
            if isinstance(data_content, dict):
                is_flat = all(isinstance(v, (int, float, str, bool)) for v in data_content.values())
                if is_flat:
                    csv_path = exp_folder / f"{filename_base}.csv"
                    try:
                        with open(csv_path, 'w', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=data_content.keys())
                            writer.writeheader()
                            writer.writerow(data_content)
                    except Exception: pass 

            session.commit()
            return attachment.id
        finally: session.close()