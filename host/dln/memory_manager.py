# host/dln/memory_manager.py
import chromadb
from pathlib import Path
import logging

log = logging.getLogger(__name__)

class MemoryManager:
    """
    Handles semantic indexing and retrieval of experimental records 
    using ChromaDB.
    """
    def __init__(self, base_dir=".talos"):
        self.base_dir = Path(base_dir).resolve()
        self.persist_path = self.base_dir / "vector_store"
        
        # Initialize persistent client
        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        
        # Get or create the collection for experiment summaries
        self.collection = self.client.get_or_create_collection(
            name="experimental_records",
            metadata={"hnsw:space": "cosine"}
        )

    def index_experiment(self, exp_id, text_content, metadata=None):
        """
        Adds an experiment's narrative to the vector store.
        """
        try:
            self.collection.add(
                ids=[exp_id],
                documents=[text_content],
                metadatas=[metadata or {}]
            )
            return True
        except Exception as e:
            log.error(f"Failed to index experiment {exp_id}: {e}")
            return False

    def search_semantic(self, query, n_results=3):
        """
        Returns the most relevant past experiments based on a query.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            formatted_results = []
            if results['documents'] and len(results['documents']) > 0:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        "id": results['ids'][0][i],
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i]
                    })
            return formatted_results
        except Exception as e:
            log.error(f"Semantic search failed: {e}")
            return []