import logging
from typing import List
from langchain_community.graphs import Neo4jGraph
from langchain_community.graphs.graph_document import GraphDocument
from config.settings import settings

logger = logging.getLogger(__name__)

class GraphStoreManager:
    """
    Manages the connection and interaction with the Neo4j Graph Database.
    
    Theory:
    Neo4j stores data as Nodes (Entities) and Edges (Relationships). This structure 
    is incredibly efficient for multi-hop queries (e.g., finding the organization 
    a person works for, and then the products that organization created).
    
    Design Decisions:
    - We use LangChain's Neo4jGraph wrapper to abstract connection handling.
    - We provide a method to cleanly insert GraphDocuments that were generated 
      by our GraphExtractor.
    """
    
    def __init__(self):
        logger.info(f"Connecting to Neo4j at {settings.neo4j_uri}...")
        try:
            self.graph = Neo4jGraph(
                url=settings.neo4j_uri,
                username=settings.neo4j_username,
                password=settings.neo4j_password
            )
            # Refresh schema to ensure we are up to date
            self.graph.refresh_schema()
            logger.info("Successfully connected to Neo4j.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j. Is the database running? Error: {str(e)}")
            raise e

    def add_documents(self, graph_documents: List[GraphDocument]) -> None:
        """
        Inserts the extracted nodes and relationships into Neo4j.
        """
        logger.info(f"Adding {len(graph_documents)} graph documents to Neo4j...")
        try:
            # We use baseEntityLabel to automatically group all entities under a common label
            # This makes generic graph retrieval easier later.
            self.graph.add_graph_documents(
                graph_documents, 
                baseEntityLabel=True,
                include_source=True # Adds original chunk text to nodes if possible
            )
            # Refresh schema so the LLM is aware of the new nodes/relationships during querying
            self.graph.refresh_schema()
            logger.info("Successfully added graph documents to Neo4j.")
        except Exception as e:
            logger.error(f"Error adding documents to Neo4j: {str(e)}")
            raise e
            
    def get_schema(self) -> str:
        """Returns the current schema of the graph (useful for Cypher generation)."""
        return self.graph.get_schema()
