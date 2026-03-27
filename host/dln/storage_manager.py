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

# --- Existing Schema (SchemaInfo, Experiment, Entry, Attachment) ---
# [Keep existing classes exactly as they were...]

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
    status = Column(String(50))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    world_model = Column(JSON)
    entries = relationship("Entry", back_populates="experiment", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="experiment", cascade="all, delete-orphan")

class Entry(Base):
    __tablename__ = 'entries'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey('experiments.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    entry_type = Column(String(50))
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
    data_type = Column(String(50))
    metadata_json = Column(JSON)
    experiment = relationship("Experiment", back_populates="attachments")
    entry = relationship("Entry", back_populates="attachments")

# --- NEW SCHEMA FOR PROTOCOLS ---

class Protocol(Base):
    __tablename__ = 'protocols'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    steps = relationship("ProtocolStep", back_populates="protocol", order_by="ProtocolStep.step_number", cascade="all, delete-orphan")

class ProtocolStep(Base):
    __tablename__ = 'protocol_steps'
    id = Column(Integer, primary_key=True, autoincrement=True)
    protocol_id = Column(String(36), ForeignKey('protocols.id'))
    step_number = Column(Integer)
    device = Column(String(50))
    command = Column(String(100))
    args = Column(JSON)
    protocol = relationship("Protocol", back_populates="steps")

# --- Manager Logic Update ---

class StorageManager:
    SCHEMA_VERSION = 2 # Increment version

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
                v.version = self.SCHEMA_VERSION
                session.commit()
        finally:
            session.close()

    # [Keep existing Experiment/Entry/Artifact methods...]

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

    def update_experiment(self, exp_id, **kwargs):
        session = self.Session()
        try:
            exp = session.query(Experiment).filter_by(id=exp_id).first()
            if exp:
                for key, value in kwargs.items():
                    if hasattr(exp, key): setattr(exp, key, value)
                if kwargs.get('status') in ('completed', 'failed', 'aborted'): exp.end_time = datetime.utcnow()
                session.commit()
        finally: session.close()

    def log_entry(self, exp_id, entry_type, content):
        session = self.Session()
        try:
            entry = Entry(experiment_id=exp_id, entry_type=entry_type, content=content)
            session.add(entry)
            session.commit()
            return entry.id
        finally: session.close()

    def save_artifact(self, exp_id, entry_id, device, command, payload):
        session = self.Session()
        try:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_suffix = str(uuid.uuid4())[:8]
            filename_base = f"data_{timestamp_str}_{unique_suffix}"
            exp_folder = self.storage_path / exp_id
            exp_folder.mkdir(parents=True, exist_ok=True)
            json_path = exp_folder / f"{filename_base}.json"
            with open(json_path, 'w') as f: json.dump(payload, f, indent=2)
            metadata = payload.get('metadata', {})
            attachment = Attachment(experiment_id=exp_id, entry_id=entry_id, filename=f"{filename_base}.json",
                                    file_path=str(json_path), data_type=metadata.get('data_type', 'unknown'),
                                    metadata_json=metadata)
            session.add(attachment)
            data_content = payload.get('data', {})
            if isinstance(data_content, dict):
                is_flat = all(isinstance(v, (int, float, str, bool)) for v in data_content.values())
                if is_flat:
                    csv_path = exp_folder / f"{filename_base}.csv"
                    try:
                        with open(csv_path, 'w', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=data_content.keys()); writer.writeheader(); writer.writerow(data_content)
                    except Exception: pass 
            session.commit()
            return attachment.id
        finally: session.close()

    # --- NEW PROTOCOL METHODS ---

    def save_protocol(self, name, description, plan_list):
        """Saves a plan as a named protocol."""
        session = self.Session()
        try:
            # Upsert logic: Delete existing protocol with same name
            existing = session.query(Protocol).filter_by(name=name).first()
            if existing: session.delete(existing)
            
            proto = Protocol(name=name, description=description)
            session.add(proto)
            session.flush() # Get ID
            
            for idx, step_data in enumerate(plan_list):
                step = ProtocolStep(
                    protocol_id=proto.id,
                    step_number=idx + 1,
                    device=step_data.get('device'),
                    command=step_data.get('command'),
                    args=step_data.get('args')
                )
                session.add(step)
            session.commit()
            return proto.id
        finally: session.close()

    def load_protocol(self, name):
        """Retrieves plan steps by protocol name."""
        session = self.Session()
        try:
            proto = session.query(Protocol).filter_by(name=name).first()
            if not proto: return None
            return [
                {"device": s.device, "command": s.command, "args": s.args} 
                for s in proto.steps
            ]
        finally: session.close()

    def list_protocols(self):
        """Returns a list of all protocol names and descriptions."""
        session = self.Session()
        try:
            protos = session.query(Protocol).all()
            return [{"name": p.name, "description": p.description} for p in protos]
        finally: session.close()