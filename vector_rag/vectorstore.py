import os
from typing import List, Literal, Any
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from langchain_chroma import Chroma
import logging

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    Manages creation and loading of Vector Databases (FAISS or Chroma).
    
    Theory:
    - FAISS (Facebook AI Similarity Search): Excellent for in-memory, highly optimized 
      similarity search. Requires saving/loading to disk manually.
    - ChromaDB: A full-fledged vector database, persistent by default, built specifically 
      for AI workloads. Great for metadata filtering.
      
    Design Decisions:
    - Abstract the vector database layer so the rest of the application doesn't care 
      whether it's FAISS or Chroma.
    - Persist databases to disk so we don't re-embed the PDF every time the script runs.
    """
    
    def __init__(
        self, 
        db_type: Literal["faiss", "chroma"], 
        embeddings: Embeddings,
        persist_dir: str = "./db"
    ):
        self.db_type = db_type
        self.embeddings = embeddings
        self.persist_dir = persist_dir
        
        # Ensure persist directory exists
        os.makedirs(self.persist_dir, exist_ok=True)
        
    def _get_path(self) -> str:
        """Returns the specific path for the chosen DB type."""
        return os.path.join(self.persist_dir, self.db_type)

    def create_and_save(self, chunks: List[Document]) -> Any:
        """
        Embeds chunks, stores them in the DB, and saves to disk.
        """
        path = self._get_path()
        logger.info(f"Creating {self.db_type} vector database at {path} with {len(chunks)} chunks...")
        
        if self.db_type == "faiss":
            vectorstore = FAISS.from_documents(chunks, self.embeddings)
            vectorstore.save_local(path)
            return vectorstore
            
        elif self.db_type == "chroma":
            vectorstore = Chroma.from_documents(
                documents=chunks, 
                embedding=self.embeddings,
                persist_directory=path
            )
            return vectorstore
            
        else:
            raise ValueError(f"Unsupported Vector DB type: {self.db_type}")

    def load(self) -> Any:
        """
        Loads an existing DB from disk. Returns None if it doesn't exist.
        """
        path = self._get_path()
        
        if self.db_type == "faiss":
            if not os.path.exists(os.path.join(path, "index.faiss")):
                logger.warning(f"No FAISS index found at {path}")
                return None
            logger.info(f"Loading FAISS database from {path}")
            # allow_dangerous_deserialization is required for newer FAISS versions if trusting the source
            return FAISS.load_local(path, self.embeddings, allow_dangerous_deserialization=True)
            
        elif self.db_type == "chroma":
            if not os.path.exists(path):
                logger.warning(f"No Chroma database found at {path}")
                return None
            logger.info(f"Loading Chroma database from {path}")
            return Chroma(persist_directory=path, embedding_function=self.embeddings)
            
        return None
