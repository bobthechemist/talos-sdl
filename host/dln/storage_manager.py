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

# --- Schema Definitions ---

class SchemaInfo(Base):
    __tablename__ = 'schema_info'
    version = Column(Integer, primary_key=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class Experiment(Base):
    __tablename__ = 'experiments'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255))
    objective = Column(Text)
    summary = Column(Text)
    status = Column(String(50))  # running, completed, failed, aborted
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    world_model = Column(JSON)  # Store the snapshot of reagents/config
    
    entries = relationship("Entry", back_populates="experiment", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="experiment", cascade="all, delete-orphan")

class Entry(Base):
    __tablename__ = 'entries'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey('experiments.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    entry_type = Column(String(50))  # prompt, plan, observation, analysis, error
    content = Column(JSON)
    
    experiment = relationship("Experiment", back_populates="entries")
    attachments = relationship("Attachment", back_populates="entry", cascade="all, delete-orphan")

class Attachment(Base):
    __tablename__ = 'attachments'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey('experiments.id'))
    entry_id = Column(String(36), ForeignKey('entries.id'), nullable=True)
    filename = Column(String(255))
    file_path = Column(String(512))
    data_type = Column(String(50)) # spectrum, settings, calibration
    metadata_json = Column(JSON)

    experiment = relationship("Experiment", back_populates="attachments")
    entry = relationship("Entry", back_populates="attachments")

# --- Manager Logic ---

class StorageManager:
    SCHEMA_VERSION = 1

    def __init__(self, base_dir=".talos"):
        self.base_dir = Path(base_dir).resolve()
        self.db_path = self.base_dir / "lab_notebook.db"
        self.storage_path = self.base_dir / "data_storage"
        
        self._ensure_dirs()
        
        # SQLite URL requires 3 slashes for a relative path or 4 for absolute.
        # Using absolute path for robustness.
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
            # Initialize version if not present
            if not session.query(SchemaInfo).first():
                session.add(SchemaInfo(version=self.SCHEMA_VERSION))
                session.commit()
        finally:
            session.close()

    # --- Experiment Operations ---

    def create_experiment(self, title, objective=None, world_model=None):
        session = self.Session()
        try:
            exp = Experiment(
                title=title,
                objective=objective,
                status="running",
                world_model=world_model
            )
            session.add(exp)
            session.commit()
            exp_id = exp.id
            
            # Create a dedicated folder for this experiment's files
            (self.storage_path / exp_id).mkdir(parents=True, exist_ok=True)
            return exp_id
        finally:
            session.close()

    def update_experiment(self, exp_id, **kwargs):
        session = self.Session()
        try:
            exp = session.query(Experiment).filter_by(id=exp_id).first()
            if exp:
                for key, value in kwargs.items():
                    if hasattr(exp, key):
                        setattr(exp, key, value)
                if kwargs.get('status') in ('completed', 'failed', 'aborted'):
                    exp.end_time = datetime.utcnow()
                session.commit()
        finally:
            session.close()

    # --- Entry Logging ---

    def log_entry(self, exp_id, entry_type, content):
        """Records a chat turn, plan, or hardware response."""
        session = self.Session()
        try:
            entry = Entry(
                experiment_id=exp_id,
                entry_type=entry_type,
                content=content
            )
            session.add(entry)
            session.commit()
            return entry.id
        finally:
            session.close()

    # --- Artifact / File Handling (Registry Replacement) ---

    def save_artifact(self, exp_id, entry_id, device, command, payload):
        """
        Saves a data payload to disk and links it to the database.
        """
        session = self.Session()
        try:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_suffix = str(uuid.uuid4())[:8]
            filename_base = f"data_{timestamp_str}_{unique_suffix}"
            
            exp_folder = self.storage_path / exp_id
            exp_folder.mkdir(parents=True, exist_ok=True)
            
            json_path = exp_folder / f"{filename_base}.json"
            
            # 1. Save JSON
            with open(json_path, 'w') as f:
                json.dump(payload, f, indent=2)
                
            # 2. Add to DB
            metadata = payload.get('metadata', {})
            attachment = Attachment(
                experiment_id=exp_id,
                entry_id=entry_id,
                filename=f"{filename_base}.json",
                file_path=str(json_path),
                data_type=metadata.get('data_type', 'unknown'),
                metadata_json=metadata
            )
            session.add(attachment)
            
            # 3. Best-effort CSV
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
                    except Exception:
                        pass 

            session.commit()
            return attachment.id
        finally:
            session.close()