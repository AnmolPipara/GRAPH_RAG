import logging
import os
from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from config.settings import settings
from vector_rag.loader import PDFLoader
from vector_rag.chunker import DocumentChunker
from vector_rag.embeddings import EmbeddingsFactory
from vector_rag.vectorstore import VectorStoreManager
from vector_rag.retriever import RetrieverManager, RetrievalOptions
from utils.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

class VectorRAGPipeline:
    """
    End-to-End Vector Database Retrieval-Augmented Generation Pipeline.
    
    Theory:
    The RAG pattern involves taking a user's question, searching for relevant 
    information (context) in an external database, and passing both the question 
    and the context to an LLM to generate a grounded answer.
    
    Design Decisions:
    - Modular architecture allows swapping components (e.g., changing embedding model 
      or Vector DB) without rewriting the core pipeline logic.
    - Utilizes LCEL (LangChain Expression Language) for building the QA chain to ensure 
      readability, async support, and easy streaming later if needed.
    """
    
    def __init__(self):
        self.embeddings = EmbeddingsFactory.get_embeddings(settings.embedding_model)
        self.vector_store_manager = VectorStoreManager(
            db_type=settings.vector_db_type,
            embeddings=self.embeddings,
            persist_dir=settings.vector_db_dir
        )
        self.retriever_manager = None
        self.qa_chain = None
        
        # Load DB if it exists
        vs = self.vector_store_manager.load()
        if vs:
            self.retriever_manager = RetrieverManager(vs)
            self._build_chain()
            
    def ingest_document(self, pdf_path: str, chunking_method: str = "recursive") -> None:
        """
        Runs the ingestion pipeline: Load -> Chunk -> Embed -> Store.
        """
        logger.info(f"Starting ingestion for {pdf_path}")
        
        # 1. Load
        loader = PDFLoader(pdf_path)
        docs = loader.load()
        
        # 2. Chunk
        chunker = DocumentChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            method=chunking_method,
            embedding_model_name=settings.embedding_model
        )
        chunks = chunker.chunk_documents(docs)
        
        # 3 & 4. Embed and Store
        vs = self.vector_store_manager.create_and_save(chunks)
        
        # Update retriever and chain
        self.retriever_manager = RetrieverManager(vs)
        self._build_chain()
        logger.info("Ingestion complete.")

    def _format_docs(self, docs: List[Document]) -> str:
        """Helper to format retrieved documents into a single string for the prompt."""
        formatted = []
        for d in docs:
            page = d.metadata.get("page", "Unknown")
            formatted.append(f"--- [Page {page}] ---\n{d.page_content}")
        return "\n\n".join(formatted)

    def _build_chain(self) -> None:
        """Builds the LCEL QA Chain."""
        llm = LLMFactory.get_llm()
        
        # Define the prompt template
        template = """You are an expert research assistant. Use the following pieces of retrieved context to answer the user's question. 
        If you don't know the answer, just say that you don't know, don't try to make up an answer.
        Always cite the page numbers if provided in the context.

        Context:
        {context}

        Question: {question}

        Answer:"""
        prompt = PromptTemplate.from_template(template)
        
        # Configure retriever (default similarity)
        retriever_options = RetrievalOptions(k=settings.top_k, search_type="similarity")
        retriever = self.retriever_manager.get_retriever(retriever_options)
        
        # Build LCEL chain
        self.qa_chain = (
            {"context": retriever | self._format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

    def query(self, question: str) -> Dict[str, Any]:
        """
        Executes a query against the Vector RAG system.
        """
        if not self.qa_chain or not self.retriever_manager:
            raise RuntimeError("Pipeline is not initialized. Please ingest a document first.")
            
        logger.info(f"Querying Vector RAG: {question}")
        
        # We retrieve separately as well to return sources to the user
        retriever_options = RetrievalOptions(k=settings.top_k)
        source_docs = self.retriever_manager.retrieve(question, retriever_options)
        
        # Execute QA chain
        answer = self.qa_chain.invoke(question)
        
        return {
            "answer": answer,
            "sources": source_docs
        }

if __name__ == "__main__":
    # Setup basic logging for testing
    logging.basicConfig(level=logging.INFO)
    print("Vector RAG Pipeline initialized.")
