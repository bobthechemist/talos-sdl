# dln/_vector_store.py
import os
import chromadb
#from sentence_transformers import SentenceTransformer
import chromadb.utils.embedding_functions as embedding_functions

class VectorStoreManager:
    """A wrapper class for ChromaDB and sentence-transformer interactions."""

    def __init__(self, db_path: str):
        chroma_data_path = os.path.join(os.path.dirname(db_path), "chroma_db")
        os.makedirs(chroma_data_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=chroma_data_path)
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()

    def get_collection_name(self, session_id: int) -> str:
        return f"session_{session_id}"

    def get_or_create_collection(self, session_id: int):
        """Gets or creates a ChromaDB collection for a given session."""
        return self.client.get_or_create_collection(
                    name=self.get_collection_name(session_id),
                    embedding_function=self.emb_fn
                )

    def add_entry(self, collection, document: str, metadata: dict, doc_id: int):
        """Generates an embedding and adds/updates a document in a ChromaDB collection."""
        # Use the lazily loaded model
        collection.upsert(
            documents=[document],
            metadatas=[metadata],
            ids=[str(doc_id)]
        )

    def query(self, collection, query_text: str, n_results: int = 5):
        """Queries a ChromaDB collection for similar documents."""
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )
        return results