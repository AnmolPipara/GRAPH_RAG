from langchain_huggingface import HuggingFaceEmbeddings
import logging

logger = logging.getLogger(__name__)

class EmbeddingsFactory:
    """
    Factory class to instantiate different embedding models.
    
    Theory:
    Different embedding models capture semantic meaning differently. 
    - BAAI/bge-large-en-v1.5: Strong general-purpose English embeddings.
    - intfloat/e5-large-v2: Great for asymmetric retrieval (query to document).
    - nomic-ai/nomic-embed-text-v1.5: High context length and strong performance.
    - sentence-transformers/all-mpnet-base-v2: Very popular, balanced speed/performance model.
    
    Design Decisions:
    - Centralizes embedding initialization.
    - Returns a LangChain Embeddings interface compatible with any VectorStore.
    - Easily extendable to add OpenAI or Google Embeddings later if needed.
    """
    
    MODEL_MAPPING = {
        "bge": "BAAI/bge-large-en-v1.5",
        "e5": "intfloat/e5-large-v2",
        "nomic": "nomic-ai/nomic-embed-text-v1.5",
        "mpnet": "sentence-transformers/all-mpnet-base-v2"
    }

    @staticmethod
    def get_embeddings(model_alias: str) -> HuggingFaceEmbeddings:
        """
        Returns an initialized HuggingFaceEmbeddings object.
        """
        model_name = EmbeddingsFactory.MODEL_MAPPING.get(model_alias.lower())
        
        if not model_name:
            # If they provided a raw huggingface model path, use it directly
            model_name = model_alias
            
        logger.info(f"Initializing Embedding model: {model_name}")
        
        # We specify the model_kwargs to ensure it runs on CPU or GPU based on availability
        # By default HuggingFaceEmbeddings uses PyTorch which handles this automatically
        model_kwargs = {'device': 'cpu'} # Change to 'cuda' if GPU is available
        encode_kwargs = {'normalize_embeddings': True} # Essential for cosine similarity
        
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )
