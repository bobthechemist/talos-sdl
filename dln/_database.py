# dln/_database.py

import os
# ADD THIS IMPORT
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base

def get_db_engine(db_path: str):
    """Creates and configures the SQLAlchemy engine for SQLite."""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # Enable WAL mode for better concurrency
    engine = create_engine(
        f"sqlite:///{db_path}?mode=wal",
        connect_args={"check_same_thread": False},
        future=True
    )
    # Enforce foreign key constraints in SQLite for every connection
    # This is the modern, correct way to execute a raw SQL string.
    with engine.connect() as connection:
        # CHANGED THIS LINE
        connection.execute(text("PRAGMA foreign_keys=ON"))
        # You also need to commit this change for it to take effect on the connection
        connection.commit()
    return engine

def get_session_factory(engine):
    """Sets up the SQLAlchemy Session factory."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def create_all_tables(engine):
    """Creates all tables defined in the models."""
    Base.metadata.create_all(engine)