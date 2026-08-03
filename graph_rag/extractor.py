import logging
from typing import List
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_community.graphs.graph_document import GraphDocument
from utils.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

class GraphExtractor:
    """
    Extracts Entities and Relationships from text chunks using an LLM.
    
    Theory:
    Unlike Vector RAG which retrieves chunks based on semantic similarity, GraphRAG 
    requires structuring the unstructured text into a Knowledge Graph. This is done by 
    instructing an LLM (using structured output/function calling) to identify specific 
    Entities (Nodes) and the Relationships (Edges) between them.
    
    Design Decisions:
    - We use LangChain's LLMGraphTransformer which handles the heavy lifting of prompting 
      the LLM to extract a strict schema.
    - We define explicit allowed_nodes and allowed_relationships based on the project requirements 
      to prevent the LLM from hallucinating unbounded schemas, ensuring a clean and queryable graph.
    """
    
    # Predefined schema as requested
    ALLOWED_NODES = [
        "Person", "Organization", "Product", "Technology", "Date", 
        "Country", "Location", "Research Paper", "Tool", "API", 
        "Dataset", "Framework"
    ]
    
    ALLOWED_RELATIONSHIPS = [
        "USES", "CREATED_BY", "WORKS_FOR", "BELONGS_TO", "IMPLEMENTS", 
        "DEPENDS_ON", "REFERENCES", "CONNECTED_TO", "ACQUIRED", 
        "LOCATED_IN", "PART_OF", "SUPPORTS", "RELATED_TO"
    ]

    def __init__(self):
        # We need a powerful LLM for extraction (e.g., GPT-4o or Gemini 1.5 Pro)
        # We retrieve it from our centralized factory.
        self.llm = LLMFactory.get_llm()
        
        # Initialize the graph transformer with strict schemas
        self.transformer = LLMGraphTransformer(
            llm=self.llm,
            allowed_nodes=self.ALLOWED_NODES,
            allowed_relationships=self.ALLOWED_RELATIONSHIPS,
            strict_mode=True # Forces the LLM to only use the allowed types
        )

    def extract_graph_documents(self, chunks: List[Document]) -> List[GraphDocument]:
        """
        Processes text chunks and converts them into GraphDocuments (Nodes + Relationships).
        Note: This can be time-consuming and token-intensive as it calls the LLM for every chunk.
        """
        logger.info(f"Extracting graph entities and relationships from {len(chunks)} chunks...")
        try:
            graph_documents = self.transformer.convert_to_graph_documents(chunks)
            logger.info(f"Successfully extracted graph from {len(chunks)} chunks.")
            
            # Simple logging of extraction results
            total_nodes = sum([len(doc.nodes) for doc in graph_documents])
            total_rels = sum([len(doc.relationships) for doc in graph_documents])
            logger.info(f"Extracted {total_nodes} nodes and {total_rels} relationships total.")
            
            return graph_documents
        except Exception as e:
            logger.error(f"Error during graph extraction: {str(e)}")
            raise e
