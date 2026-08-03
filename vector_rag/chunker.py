from typing import List, Literal
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
import logging

logger = logging.getLogger(__name__)

class DocumentChunker:
    """
    Handles chunking of documents using either recursive character splitting 
    or semantic chunking based on configuration.
    
    Theory:
    - Recursive Chunking: Splits text hierarchically using a list of separators 
      (paragraphs, sentences, words, chars) to keep related text together. It's fast and reliable.
    - Semantic Chunking: Groups sentences based on semantic similarity (embeddings) 
      to ensure chunks contain cohesive topics. Slower but potentially yields better retrieval.
      
    Design Decisions:
    - Supports dynamic switching between 'recursive' and 'semantic'.
    - Propagates metadata (page, source) from parent document to all its chunks automatically.
    """
    
    def __init__(
        self, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200,
        method: Literal["recursive", "semantic"] = "recursive",
        embedding_model_name: str = "BAAI/bge-large-en-v1.5"
    ):
        self.method = method
        
        if self.method == "recursive":
            self.splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ".", " ", ""]
            )
        elif self.method == "semantic":
            # Require an embedding model for semantic chunking
            embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
            self.splitter = SemanticChunker(
                embeddings, 
                breakpoint_threshold_type="percentile"
            )
        else:
            raise ValueError(f"Unknown chunking method: {method}")

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Splits a list of documents into chunks.
        """
        logger.info(f"Chunking {len(documents)} documents using {self.method} method...")
        chunks = self.splitter.split_documents(documents)
        logger.info(f"Generated {len(chunks)} chunks.")
        return chunks
