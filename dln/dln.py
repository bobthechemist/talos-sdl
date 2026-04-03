# dln/dln.py

import os
import uuid
import json
import datetime
from sqlalchemy import text
from . import _database, _vector_store, verification
from .models import ExperimentSession, ScienceLog, TransactionLog, Protocol
from .exceptions import (
    ExperimentNotStartedError,
    ExperimentAlreadyStartedError,
    ExperimentFinalizedError,
)

class DigitalLabNotebook:
    """The main interface for the Digital Lab Notebook."""

    def __init__(self, db_path: str):
        """
        Initializes the DLN. Creates database files and directories if they don't exist.

        Args:
            db_path (str): The file path for the SQLite database. Associated data 
                           (blobs, vector store) will be stored in subdirectories 
                           relative to this path.
        """
        self.db_path = db_path
        self.engine = _database.get_db_engine(db_path)
        _database.create_all_tables(self.engine)
        self.Session = _database.get_session_factory(self.engine)

        self.blob_dir = os.path.join(os.path.dirname(db_path), "blobs")
        os.makedirs(self.blob_dir, exist_ok=True)
        
        self.vector_store = _vector_store.VectorStoreManager(db_path)
        
        self.current_session_id = None
        self.current_session_status = None

    def _assert_active_session(self):
        """(Private) Ensures an experiment is active and not finalized before proceeding."""
        if self.current_session_id is None:
            raise ExperimentNotStartedError("No active experiment. Call start_experiment() first.")
        if self.current_session_status == 'finalized':
            raise ExperimentFinalizedError("The current experiment has been finalized and cannot be modified.")

    def start_experiment(self, title: str, context_json: dict) -> int:
        """
        Starts a new experiment session, making it the active session for this instance.

        Args:
            title (str): The title of the experiment.
            context_json (dict): A JSON-serializable dictionary representing the
                                 "prelab" state (e.g., environment, assets, agent info).

        Returns:
            int: The ID of the newly created experiment session.

        Raises:
            ExperimentAlreadyStartedError: If an experiment is already active on this instance.
        """
        if self.current_session_id is not None:
            raise ExperimentAlreadyStartedError(f"Session {self.current_session_id} is already active.")

        with self.Session() as session:
            new_session = ExperimentSession(title=title, context_json=context_json)
            session.add(new_session)
            session.commit()
            
            self.current_session_id = new_session.id
            self.current_session_status = new_session.status

            # Automatically log the initial context to ScienceLog
            self.log_science(entry_type="context", data={"context": context_json})
            return self.current_session_id

    def log_science(self, entry_type: str, data: dict, supersedes_id: int = None, reason: str = None) -> int:
        """
        Logs a structured, high-level entry into the Science Log.

        This is the primary method for recording observations, results, and reflections.
        To correct a previous entry, provide its ID to `supersedes_id` and a reason.

        Args:
            entry_type (str): The type of entry (e.g., 'observation', 'snapshot', 'reflection').
            data (dict): A JSON-serializable dictionary containing the entry's content.
            supersedes_id (int, optional): The ID of a previous ScienceLog entry that this
                                           entry corrects or replaces. Defaults to None.
            reason (str, optional): A description of why the entry is being superseded.
                                    Required if `supersedes_id` is provided.

        Returns:
            int: The ID of the newly created ScienceLog entry.

        Raises:
            ExperimentNotStartedError: If no experiment is active.
            ExperimentFinalizedError: If the active experiment has been finalized.
            ValueError: If `supersedes_id` is provided without a `reason`.
        """
        self._assert_active_session()
        if supersedes_id and not reason:
            raise ValueError("A reason must be provided when superseding an entry.")

        with self.Session() as session:
            log_entry = ScienceLog(
                session_id=self.current_session_id,
                entry_type=entry_type,
                data=data,
                supersedes_id=supersedes_id,
                correction_reason=reason
            )
            session.add(log_entry)
            session.commit()
            return log_entry.id

    def log_transaction(self, raw_io: str):
        """
        Logs a low-level, raw I/O string to the Transaction Log.

        Use this to record machine-to-machine communication like serial commands,
        API calls, or instrument responses without cluttering the Science Log.

        Args:
            raw_io (str): The raw string representing the I/O event.

        Raises:
            ExperimentNotStartedError: If no experiment is active.
            ExperimentFinalizedError: If the active experiment has been finalized.
        """
        self._assert_active_session()
        with self.Session() as session:
            log_entry = TransactionLog(
                session_id=self.current_session_id,
                raw_io=raw_io
            )
            session.add(log_entry)
            session.commit()

    def store_blob(self, file_data: bytes, file_name: str) -> str:
        """
        Stores binary data (e.g., images, CSVs) in the blob store for the current session.

        The file is saved with a unique name to prevent collisions. The returned path
        should be stored in a Science Log entry to link it to the experiment.

        Args:
            file_data (bytes): The binary content of the file.
            file_name (str): The original name of the file, used to create the new unique name.

        Returns:
            str: The relative path to the stored file, suitable for logging.

        Raises:
            ExperimentNotStartedError: If no experiment is active.
            ExperimentFinalizedError: If the active experiment has been finalized.
        """
        self._assert_active_session()
        session_blob_dir = os.path.join(self.blob_dir, str(self.current_session_id))
        os.makedirs(session_blob_dir, exist_ok=True)
        
        unique_filename = f"{uuid.uuid4()}-{file_name}"
        file_path = os.path.join(session_blob_dir, unique_filename)
        
        with open(file_path, "wb") as f:
            f.write(file_data)
            
        return os.path.relpath(file_path, os.path.dirname(self.db_path))

    def finalize(self, summary_text: str):
        """
        Finalizes the current experiment, making it read-only and generating an integrity hash.

        This action logs the summary, updates the vector store with all relevant entries,
        calculates a final SHA-256 hash of the session's data, and locks the session
        from further modification. The instance's active session is then reset.

        Args:
            summary_text (str): A concluding summary of the experiment.

        Raises:
            ExperimentNotStartedError: If no experiment is active.
            ExperimentFinalizedError: If the active experiment has already been finalized.
        """
        self._assert_active_session()
        
        self.log_science(entry_type='summary', data={'text': summary_text})
        self.update_reflective_log() # Call the public method
        
        with self.Session() as session:
            final_hash = verification.generate_session_hash(session, self.current_session_id)
            
            exp_session = session.get(ExperimentSession, self.current_session_id)
            exp_session.status = 'finalized'
            exp_session.end_time = datetime.datetime.utcnow()
            exp_session.final_summary = summary_text
            exp_session.final_hash = final_hash
            session.commit()

        self.current_session_id = None
        self.current_session_status = None

    def update_reflective_log(self):
        """
        Populates or updates the vector store with embeddable science logs from the current session.
        This method can be called multiple times during an active session to keep the reflective
        log up-to-date for semantic queries.
        """
        # Allow this to run for active or finalized sessions.
        # It will re-index all relevant entries for the current session ID.
        if self.current_session_id is None:
            raise ExperimentNotStartedError("No active experiment to update reflective log for.")
            
        collection = self.vector_store.get_or_create_collection(self.current_session_id)
        
        with self.Session() as session:
            # Query all relevant logs for the current session to (re)index
            logs_to_embed = session.query(ScienceLog).filter(
                ScienceLog.session_id == self.current_session_id,
                ScienceLog.entry_type.in_(['observation', 'reflection', 'summary', 'intent', 'plan']) # Include more types for RAG
            ).all()

            for log in logs_to_embed:
                document_text = json.dumps(log.data)
                self.vector_store.add_entry( # This now uses upsert
                    collection=collection,
                    document=document_text,
                    metadata={'entry_type': log.entry_type, 'id': log.id, 'session_id': self.current_session_id},
                    doc_id=log.id
                )

    def query_relational(self, sql_query: str) -> list:
        """
        Executes a read-only SQL query against the database.

        WARNING: This method executes raw SQL and is intended for advanced use.
        It does not use the ORM and provides direct, read-only access.
        Ensure queries are safe and do not attempt to modify data.

        Args:
            sql_query (str): The raw SQL query string to execute.

        Returns:
            list: A list of result rows, where each row is a tuple-like object.
        """
        with self.engine.connect() as connection:
            result = connection.execute(text(sql_query))
            return result.fetchall()

    def query_vector(self, query_text: str, session_id: int, n_results: int = 5) -> list[ScienceLog]:
        """
        Performs a semantic search on a specific experiment session.

        This method queries the Reflective Log (vector store) for entries semantically
        similar to the `query_text` and returns the full ScienceLog objects.
        For active sessions, ensure `update_reflective_log()` has been called recently
        to include the latest data.

        Args:
            query_text (str): The natural language text to search for.
            session_id (int): The ID of the experiment session to search within.
            n_results (int, optional): The maximum number of results to return. Defaults to 5.

        Returns:
            list[ScienceLog]: A list of the full ScienceLog ORM objects that are most
                              semantically similar to the query text.
        """
        # FIX: Ensure collection exists before querying.
        collection = self.vector_store.get_or_create_collection(session_id)
        
        # Check if the collection has any data before querying.
        # This prevents errors if update_reflective_log hasn't been called for this session.
        if collection.count() == 0:
            return []

        results = self.vector_store.query(collection, query_text, n_results=n_results)
        
        if not results or not results.get('ids') or not results['ids'][0]:
            return []

        log_ids = [int(id_str) for id_str in results['ids'][0]]
        
        with self.Session() as session:
            # Filter by session_id as well to ensure correctness, though vector store is per session.
            full_logs = session.query(ScienceLog).filter(
                ScienceLog.id.in_(log_ids),
                ScienceLog.session_id == session_id
            ).all()
        
        return full_logs

    def save_protocol(self, name: str, content: str) -> tuple[str, int]:
        """
        Saves a new version of a named protocol to the database.

        If a protocol with the given name already exists, this method increments the
        version number and saves it as a new entry.

        Args:
            name (str): The name of the protocol.
            content (str): The text content of the protocol.

        Returns:
            tuple[str, int]: A tuple containing the protocol's name and its new version number.
        """
        with self.Session() as session:
            latest_protocol = session.query(Protocol).filter_by(name=name).order_by(Protocol.version.desc()).first()
            
            new_version = 1
            if latest_protocol:
                new_version = latest_protocol.version + 1
            
            new_protocol = Protocol(name=name, content=content, version=new_version)
            session.add(new_protocol)
            session.commit()
            return (name, new_version)

    def get_protocol(self, name: str, version: int = None) -> Protocol | None:
        """
        Retrieves a protocol from the database.

        Args:
            name (str): The name of the protocol to retrieve.
            version (int, optional): The specific version to retrieve. If None,
                                     the latest version is returned. Defaults to None.

        Returns:
            Protocol | None: The SQLAlchemy Protocol object if found, otherwise None.
        """
        with self.Session() as session:
            query = session.query(Protocol).filter_by(name=name)
            if version:
                protocol = query.filter_by(version=version).one_or_none()
            else:
                protocol = query.order_by(Protocol.version.desc()).first()
        
        return protocol