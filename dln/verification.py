import hashlib
import json
from sqlalchemy.orm import Session
from .models import ExperimentSession, ScienceLog, TransactionLog

def _deterministic_json_dumps(data):
    """A deterministic JSON serializer."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'))

def generate_session_hash(session: Session, session_id: int) -> str:
    """
    Generates a SHA-256 hash from all logs in a session in a deterministic order.
    """
    exp_session = session.query(ExperimentSession).filter_by(id=session_id).one()
    science_logs = session.query(ScienceLog).filter_by(session_id=session_id).order_by(ScienceLog.id).all()
    transaction_logs = session.query(TransactionLog).filter_by(session_id=session_id).order_by(TransactionLog.id).all()

    hasher = hashlib.sha256()

    # 1. Hash session context
    hasher.update(_deterministic_json_dumps(exp_session.context_json).encode('utf-8'))

    # 2. Hash science logs
    for log in science_logs:
        log_str = (
            f"{log.id}|{log.timestamp.isoformat()}|{log.entry_type}|"
            f"{_deterministic_json_dumps(log.data)}|"
            f"{log.supersedes_id or ''}|{log.correction_reason or ''}"
        )
        hasher.update(log_str.encode('utf-8'))

    # 3. Hash transaction logs
    for log in transaction_logs:
        log_str = f"{log.id}|{log.timestamp.isoformat()}|{log.raw_io}"
        hasher.update(log_str.encode('utf-8'))
        
    return hasher.hexdigest()

def check_integrity(db_path: str, session_id: int) -> bool:
    """
    Standalone utility to verify the integrity of a finalized experiment session.
    """
    from ._database import get_db_engine, get_session_factory
    
    engine = get_db_engine(db_path)
    Session = get_session_factory(engine)
    
    with Session() as session:
        exp_session = session.query(ExperimentSession).filter_by(id=session_id).one_or_none()
        if not exp_session or exp_session.status != 'finalized' or not exp_session.final_hash:
            raise ValueError("Session not found, not finalized, or has no stored hash.")
            
        stored_hash = exp_session.final_hash
        recalculated_hash = generate_session_hash(session, session_id)
        
    return stored_hash == recalculated_hash