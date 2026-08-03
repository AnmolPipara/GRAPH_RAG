import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal, List


class Settings(BaseSettings):
    """Central configuration for the Vector RAG vs GraphRAG project.
    
    Model/Provider Architecture:
        - EXTRACTION: Frontier LLM (≥100B) for per-chunk knowledge extraction
        - REFINEMENT: Frontier LLM for global graph refinement pass
        - CYPHER: Model for Cypher query generation from natural language
        - ANSWER: Shared model for final answer generation (SAME for both RAG
          systems so the comparison isolates the retrieval method)
        - VLM: Vision-language model for image-based extraction
    
    Each role has a separate model name and provider, allowing mixed backends.
    NOTE: ANSWER_PROVIDER/ANSWER_MODEL are shared by BOTH RAG systems so the
    evaluation and the side-by-side app compare retrieval methods fairly.
    """

    # ── API Keys (loaded from .env) ─────────────────────────────────────
    google_api_key: str = Field("", env="GOOGLE_API_KEY")
    groq_api_key: str = Field("", env="GROQ_API_KEY")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    huggingface_api_key: str = Field("", env="HUGGINGFACE_API_KEY")
    openrouter_api_key: str = Field("", env="OPENROUTER_API_KEY")

    # ── Neo4j Settings ──────────────────────────────────────────────────
    neo4j_uri: str = Field("bolt://localhost:7687", env="NEO4J_URI")
    neo4j_username: str = Field("neo4j", env="NEO4J_USERNAME")
    neo4j_password: str = Field("password", env="NEO4J_PASSWORD")

    # ── Graph RAG — Extraction Model (Frontier, ≥100B) ──────────────────
    EXTRACTION_MODEL: str = Field(
        "llama-3.3-70b-versatile",
        description="Frontier LLM for per-chunk knowledge extraction"
    )
    EXTRACTION_PROVIDER: str = Field(
        "groq",
        description="API provider for extraction: openrouter | openai | google | groq"
    )
    EXTRACTION_TEMPERATURE: float = Field(
        0.1,
        description="Slight temperature (0.1) allows more diverse entity identification while staying close to deterministic"
    )
    EXTRACTION_MAX_RETRIES: int = Field(
        5,
        description="Max retries per chunk extraction on transient errors"
    )

    # ── Graph RAG — Refinement Model (Frontier, same or equivalent) ─────
    REFINEMENT_MODEL: str = Field(
        "llama-3.3-70b-versatile",
        description="Frontier LLM for global graph refinement pass"
    )
    REFINEMENT_PROVIDER: str = Field(
        "groq",
        description="API provider for refinement"
    )
    REFINEMENT_BATCH_SIZE: int = Field(
        50,
        description="Number of entities per refinement batch"
    )

    # ── Graph RAG — Cypher Generation Model ─────────────────────────────
    # NOTE: kept on the SAME provider+model as ANSWER for a fair comparison
    #
    # CURRENT (default): Groq llama-3.3-70b-versatile — free, no HuggingFace
    #   credits needed. Daily cap is 100K TPD which cannot cover a full 60x2
    #   benchmark run (~200K+ tokens) — only partial runs fit in one day.
    # BIG-MODEL ALTERNATIVE (prepaid): Qwen/Qwen3.5-397B-A17B via the
    #   HuggingFace Inference Router (reasoning model), fully wired through
    #   utils/hf_client.py (reasoning-aware, reasoning_effort=low to cut
    #   thinking cost ~10x). To use it, set provider="huggingface" and model
    #   "Qwen/Qwen3.5-397B-A17B".
    CYPHER_MODEL: str = Field(
        "llama-3.3-70b-versatile",
        description="Model for Cypher query generation (same as ANSWER for fair eval)"
    )
    CYPHER_PROVIDER: str = Field(
        "groq",
        description="API provider for Cypher generation (groq free fallback | huggingface router)"
    )

    # ── Graph RAG — Answer Generation Model (shared, fair comparison) ───
    # Both Vector RAG and GraphRAG generate answers with this exact model
    # so the ONLY difference between the systems is the retrieval method.
    # Default: Groq llama-3.3-70b-versatile (free, no HuggingFace credits
    # needed). To use the HF router instead, set provider="huggingface" and
    # model "Qwen/Qwen3.5-397B-A17B" (see CYPHER section for details).
    ANSWER_MODEL: str = Field(
        "llama-3.3-70b-versatile",
        description="Model for final answer generation (same for both RAG systems)"
    )
    ANSWER_PROVIDER: str = Field(
        "groq",
        description="API provider for answer generation (groq free fallback | huggingface router)"
    )

    # ── Graph RAG — Vision Model ────────────────────────────────────────
    VLM_MODEL: str = Field(
        "gpt-4o",
        description="VLM model for image-based extraction"
    )
    VLM_PROVIDER: str = Field(
        "openai",
        description="API provider for VLM"
    )

    # ── Graph RAG — PDF & Chunking ──────────────────────────────────────
    PDF_PATH: str = Field(
        "./iso-20022-payments-guide-2025-en.pdf",
        description="Path to the source PDF for graph extraction"
    )
    CHUNK_SIZE_GRAPH: int = Field(
        3000,
        description="Target characters per semantic batch for exhaustive extraction. Smaller = more granular entity extraction."
    )
    CHUNK_OVERLAP_GRAPH: int = Field(
        500,
        description="Overlap between semantic sections to maintain context across chunk boundaries"
    )
    MIN_IMAGE_SIZE: int = Field(
        100,
        description="Minimum pixel dimension for valid images"
    )
    CACHE_DIR: str = Field(
        "./data/cache",
        description="Directory for caching LLM extractions to allow resumption"
    )

    # ── Graph RAG — Extraction Limits ───────────────────────────────────
    MAX_ENTITIES_PER_CHUNK: int = Field(
        500,
        description="Max entities the LLM should extract per chunk"
    )
    MAX_RELATIONSHIPS_PER_CHUNK: int = Field(
        500,
        description="Max relationships the LLM should extract per chunk"
    )

    # ── Graph RAG — Entity & Relationship Schema ────────────────────────
    ENTITY_TYPES: List[str] = Field(
        default_factory=lambda: [
            "Organization", "Person", "Country", "Location", "Standard",
            "Specification", "Protocol", "Technology", "Framework", "Software",
            "API", "PaymentScheme", "PaymentRole", "FinancialInstitution",
            "BusinessProcess", "Workflow", "Rule", "ValidationRule",
            "BusinessConcept", "TechnicalConcept", "XMLMessage", "MessageType",
            "BusinessComponent", "DataElement", "XMLElement", "Identifier",
            "Account", "IBAN", "BIC", "Currency", "Code", "Product",
            "Service", "Dataset", "Metric", "Unit", "Document", "Section",
            "Table", "Figure", "Diagram", "Date", "Version", "Event",
            # Extended types discovered during extraction
            "Subsection", "Contact", "SocialMedia", "AddressType",
            "DocumentSection", "System", "Process"
        ],
        description="Allowed entity types for the knowledge graph schema"
    )

    RELATIONSHIP_TYPES: List[str] = Field(
        default=[
            # Core structural
            "PART_OF", "CONTAINS", "HAS_COMPONENT", "BELONGS_TO",
            # Creation & ownership
            "CREATED", "CREATED_BY", "OWNS", "OWNED_BY",
            "PUBLISHES", "PUBLISHED_BY", "DEVELOPS", "DEVELOPED_BY",
            # Organizational
            "WORKS_FOR", "MANAGES", "LOCATED_IN", "OPERATES",
            # Usage & implementation
            "USES", "USED_BY", "IMPLEMENTS", "IMPLEMENTED_BY",
            "SUPPORTS", "SUPPORTED_BY", "ENABLES", "ENABLED_BY",
            "PROVIDES", "PROVIDED_BY", "REQUIRES", "REQUIRED_BY",
            # Regulation & governance
            "REGULATES", "REGULATED_BY", "AUTHORIZES", "AUTHORIZED_BY",
            "VALIDATES", "APPROVED_BY", "COMPLIES_WITH",
            # Financial / domain-specific
            "PAYMENT_TO", "PAYMENT_FROM", "INITIATES", "PROCESSES",
            "SETTLES", "TRANSFERS", "RECEIVES", "SENDS",
            "DEBITS", "CREDITS", "CHARGES", "PAYS",
            # Versioning & succession
            "HAS_VERSION", "REPLACES", "REPLACED_BY", "SUCCEEDS",
            "PRECEDED_BY", "BASED_ON", "DERIVED_FROM",
            # Reference & association
            "REFERENCES", "RELATED_TO", "ASSOCIATED_WITH",
            "MENTIONS", "IDENTIFIED_BY", "DEFINED_BY", "SPECIFIED_BY",
            # Collaboration
            "WORKS_WITH", "COLLABORATES_WITH", "INTEGRATES",
            # Transformation & communication
            "CONVERTS", "FORMATS", "TRANSMITS", "EXCHANGES",
            "NOTIFIES", "GENERATES", "EXECUTES", "PERFORMS",
            # Coverage
            "COVERS", "APPLIES_TO", "MAPPED_TO", "HARMONIZES",
            # Status
            "HAS_STATUS", "MAINTAINS", "HANDLES",
            # Release
            "RELEASED", "RELEASED_BY", "ISSUED_BY", "FUNDED_BY",
            # Acquisition
            "ACQUIRED", "PRODUCES",
            # Extended types discovered during extraction
            "FOLLOWS", "EXCLUDES", "USED_IN", "MIGRATED_TO",
            "RECOMMENDS", "INCLUDES", "FLOWS_TO",
        ]
    )

    # ── Vector RAG Settings (unchanged) ─────────────────────────────────
    llm_provider: str = Field(
        "groq",
        description="Default LLM provider for the Vector RAG pipeline chain "
                    "(kept on the same provider as ANSWER for fair comparison; "
                    "groq free fallback uses groq_model)"
    )
    gemini_model: str = Field("gemini-2.0-flash", description="Gemini model name")
    groq_model: str = Field(
        "llama-3.3-70b-versatile",
        description="Groq model name (free fallback provider)"
    )
    openrouter_model: str = Field(
        "meta-llama/llama-3.3-70b-instruct",
        description="OpenRouter model name (backup provider)"
    )
    huggingface_model: str = Field(
        "Qwen/Qwen3.5-397B-A17B",
        description="HuggingFace Inference Router model name (shared for fair comparison)"
    )

    # ── Generation Limits ───────────────────────────────────────────────
    max_tokens_answer: int = Field(
        1024,
        description="Max output tokens for answer generation (bounded to fit quota)"
    )
    max_tokens_cypher: int = Field(
        1024,
        description="Max output tokens for Cypher generation (multi-hop queries need headroom)"
    )
    openai_model: str = Field("gpt-4o", description="OpenAI model name")
    temperature: float = Field(0.0, description="Temperature for LLM generation")
    chunk_size: int = Field(1000, description="Size of text chunks")
    chunk_overlap: int = Field(200, description="Overlap between chunks")
    embedding_model: str = Field(
        "sentence-transformers/all-mpnet-base-v2",
        description="Sentence transformer model for embeddings"
    )
    vector_db_type: Literal["faiss", "chroma"] = Field(
        "faiss", description="Vector database to use"
    )
    top_k: int = Field(5, description="Number of chunks to retrieve")
    data_dir: str = Field("./data", description="Directory containing PDFs")
    vector_db_dir: str = Field(
        "./vector_rag/db", description="Directory to store vector db persistence"
    )

    # ── Pydantic model config ───────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Helper Methods ──────────────────────────────────────────────────
    def get_api_key_for_provider(self, provider: str) -> str:
        """Return the appropriate API key for the given provider."""
        provider = provider.lower()
        key_map = {
            "openrouter": self.openrouter_api_key,
            "openai": self.openai_api_key,
            "google": self.google_api_key,
            "groq": self.groq_api_key,
            "huggingface": self.huggingface_api_key,
        }
        key = key_map.get(provider, "")
        if not key:
            raise ValueError(
                f"No API key configured for provider '{provider}'. "
                f"Set the corresponding environment variable in .env"
            )
        return key

    def get_base_url_for_provider(self, provider: str) -> str:
        """Return the base URL for the given provider's OpenAI-compatible endpoint."""
        provider = provider.lower()
        url_map = {
            "openrouter": "https://openrouter.ai/api/v1",
            "openai": "https://api.openai.com/v1",
            "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "groq": "https://api.groq.com/openai/v1",
            "huggingface": "https://router.huggingface.co/v1",
        }
        url = url_map.get(provider)
        if url is None:
            raise ValueError(f"Unknown provider: '{provider}'")
        return url


# Initialize settings singleton
settings = Settings()

if __name__ == "__main__":
    print(f"Extraction Model    : {settings.EXTRACTION_MODEL}")
    print(f"Extraction Provider : {settings.EXTRACTION_PROVIDER}")
    print(f"Refinement Model    : {settings.REFINEMENT_MODEL}")
    print(f"Answer Model        : {settings.ANSWER_MODEL}")
    print(f"Answer Provider     : {settings.ANSWER_PROVIDER}")
    print(f"Neo4j URI           : {settings.neo4j_uri}")
    print(f"Entity Types        : {len(settings.ENTITY_TYPES)} types")
    print(f"Relationship Types  : {len(settings.RELATIONSHIP_TYPES)} types")
