import os
import fitz  # PyMuPDF
from typing import List, Dict, Any
from langchain_core.documents import Document
import logging

logger = logging.getLogger(__name__)

class PDFLoader:
    """
    Loads PDF documents and extracts text using PyMuPDF.
    
    Theory:
    PyMuPDF (fitz) is known for its speed and accuracy in extracting text, 
    tables, and metadata from PDF files compared to other Python libraries.
    
    Design Decisions:
    - We return Langchain Document objects to seamlessly integrate with the rest 
      of the LangChain ecosystem (chunkers, vector stores).
    - We attach page number and source file path as metadata to support source citation.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"PDF file not found at {self.file_path}")
            
    def load(self) -> List[Document]:
        """
        Extracts text from the PDF and returns a list of Langchain Documents (one per page).
        """
        documents = []
        try:
            # Open the PDF file
            pdf_document = fitz.open(self.file_path)
            
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                text = page.get_text("text")
                
                # Only add pages with actual text
                if text.strip():
                    metadata = {
                        "source": self.file_path,
                        "page": page_num + 1  # 1-indexed for human readability
                    }
                    doc = Document(page_content=text, metadata=metadata)
                    documents.append(doc)
                    
            logger.info(f"Successfully loaded {len(documents)} pages from {self.file_path}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading PDF {self.file_path}: {str(e)}")
            raise e
