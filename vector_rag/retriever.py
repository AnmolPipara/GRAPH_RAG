from typing import Any, Dict, List
from langchain_core.documents import Document
from pydantic import BaseModel, Field

class RetrievalOptions(BaseModel):
    """Options for configuring the retriever."""
    search_type: str = Field(default="similarity", description="Type of search: 'similarity' or 'mmr'")
    k: int = Field(default=5, description="Number of documents to return")
    fetch_k: int = Field(default=20, description="Number of documents to fetch for MMR before re-ranking")
    lambda_mult: float = Field(default=0.5, description="Diversity vs relevance for MMR (0 to 1)")
    filter: Dict[str, Any] = Field(default_factory=dict, description="Metadata filters (e.g., {'page': 1})")


class RetrieverManager:
    """
    Wraps the LangChain vectorstore retriever to simplify configuration.
    
    Theory:
    - Similarity Search (KNN): Finds the closest chunks based on cosine similarity.
      Good for direct answers but can return redundant chunks.
    - MMR (Maximal Marginal Relevance): Fetches a larger pool of chunks, then 
      re-ranks them to maximize both relevance to the query AND diversity among 
      the returned chunks. Reduces redundancy.
      
    Design Decisions:
    - Exposes a clean API for swapping between Similarity and MMR at query time.
    - Allows metadata filtering (if supported by the underlying DB like Chroma).
    """
    
    def __init__(self, vectorstore: Any):
        self.vectorstore = vectorstore

    def get_retriever(self, options: RetrievalOptions = RetrievalOptions()):
        """
        Returns a configured LangChain Retriever object.
        """
        search_kwargs = {"k": options.k}
        
        if options.filter:
            search_kwargs["filter"] = options.filter
            
        if options.search_type == "mmr":
            search_kwargs["fetch_k"] = options.fetch_k
            search_kwargs["lambda_mult"] = options.lambda_mult
            
        return self.vectorstore.as_retriever(
            search_type=options.search_type,
            search_kwargs=search_kwargs
        )

    def retrieve(self, query: str, options: RetrievalOptions = RetrievalOptions()) -> List[Document]:
        """
        Directly executes a retrieval without building a chain.
        Useful for evaluation metrics (Context Precision/Recall).
        """
        retriever = self.get_retriever(options)
        return retriever.invoke(query)
