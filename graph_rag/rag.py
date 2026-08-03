import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

def main():
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    
    if not openrouter_api_key:
        print("Error: OPENROUTER_API_KEY not found in .env")
        sys.exit(1)
        
    print("Connecting to Neo4j Knowledge Graph...")
    try:
        # Load the graph schema. This strictly uses the relationships and nodes, NO vector embeddings.
        graph = Neo4jGraph(
            url=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password,
            database=neo4j_user
        )
        print("Graph connected successfully! Schema refreshed.")
    except Exception as e:
        print(f"Failed to connect to Neo4j graph: {e}")
        sys.exit(1)
        
    print("Initializing LLM (via OpenRouter) for Cypher Generation and RAG...")
    model_name = os.getenv("SLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    
    llm = ChatOpenAI(
        api_key=openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        model=model_name,
        temperature=0.0
    )
    
    # Custom Cypher Generation Prompt to prevent hanging on unbounded traversals
    CYPHER_GENERATION_TEMPLATE = """Task: Generate Cypher statement to query a graph database.

STRICT RULES:
1. Use only the provided relationship types and properties in the schema.
2. NEVER use `shortestPath`.
3. NEVER use path variables like `p=(...)`.
4. NEVER put function calls inside node property maps.
5. Filter by name in the WHERE clause using: `WHERE toLower(n.name) CONTAINS toLower("keyword")`
6. Always RETURN node properties directly (e.g., `n1.name`, `n2.name`). NEVER use `type(r)` unless you assigned a variable to the relationship with `[r]` or `[r:TYPE]`.
7. Always end with `LIMIT 20`.

TEMPLATE (follow this exact pattern):
MATCH (n1)-[r]->(n2)
WHERE toLower(n1.name) CONTAINS toLower("keyword")
RETURN n1.name, n2.name
LIMIT 20

If filtering by relationship type, name the variable:
MATCH (n1)-[r:HAS_COMPONENT]->(n2)
WHERE toLower(n1.name) CONTAINS toLower("keyword")
RETURN n1.name, n2.name
LIMIT 20

Schema:
{schema}

Do not include any explanations. Return ONLY the Cypher statement.

The question is:
{question}"""

    cypher_prompt = PromptTemplate(
        template=CYPHER_GENERATION_TEMPLATE, 
        input_variables=["schema", "question"]
    )
    
    # Create the Graph Cypher QA chain (Pure Knowledge Graph RAG)
    try:
        chain = GraphCypherQAChain.from_llm(
            graph=graph,
            cypher_llm=llm,
            qa_llm=llm,
            cypher_prompt=cypher_prompt,
            verbose=True,
            allow_dangerous_requests=True,
            top_k=5,
            return_direct=False
        )
    except Exception as e:
        print(f"Failed to initialize GraphCypherQAChain: {e}")
        sys.exit(1)
    
    print("\n" + "="*50)
    print("Pure Knowledge Graph RAG Application Initialized")
    print("No vector embeddings are being used. It relies strictly on Cypher query generation.")
    print("="*50)
    
    print("\nEntering interactive mode. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_query = input("\nEnter your query: ")
            if user_query.strip().lower() in ['exit', 'quit']:
                print("Exiting...")
                break
            if not user_query.strip():
                continue
                
            response = chain.invoke({"query": user_query})
            print("\n[AI Answer]:")
            print(response.get("result", "No result returned"))
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError during retrieval/generation: {e}")
            
    print("\nDone with Graph RAG Application.")

if __name__ == "__main__":
    main()
