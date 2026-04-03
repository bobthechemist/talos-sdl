# dln/_vector_store.py
import os
import chromadb
from sentence_transformers import SentenceTransformer

class VectorStoreManager:
    """A wrapper class for ChromaDB and sentence-transformer interactions."""

    def __init__(self, db_path: str):
        chroma_data_path = os.path.join(os.path.dirname(db_path), "chroma_db")
        os.makedirs(chroma_data_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=chroma_data_path)
        
        # Defer loading the SentenceTransformer model until it's needed
        self._model = None

    @property
    def embedding_model(self):
        """Loads the SentenceTransformer model lazily (on first access)."""
        if self._model is None:
            print("Loading SentenceTransformer model... (This may take a moment)")
            # Using a small, efficient model. This can be changed.
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            print("SentenceTransformer model loaded.")
        return self._model

    def get_collection_name(self, session_id: int) -> str:
        return f"session_{session_id}"

    def get_or_create_collection(self, session_id: int):
        """Gets or creates a ChromaDB collection for a given session."""
        collection_name = self.get_collection_name(session_id)
        return self.client.get_or_create_collection(name=collection_name)

    def add_entry(self, collection, document: str, metadata: dict, doc_id: int):
        """Generates an embedding and adds/updates a document in a ChromaDB collection."""
        # Use the lazily loaded model
        embedding = self.embedding_model.encode(document).tolist()
        collection.upsert(
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
            ids=[str(doc_id)]
        )

    def query(self, collection, query_text: str, n_results: int = 5):
        """Queries a ChromaDB collection for similar documents."""
        # Use the lazily loaded model
        query_embedding = self.embedding_model.encode(query_text).tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )
        return results