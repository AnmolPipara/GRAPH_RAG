# AI Project: Vector RAG vs GraphRAG Comparison

This project is a research-grade implementation comparing two advanced Retrieval-Augmented Generation (RAG) paradigms on the same dataset (ISO 20022 Payments Guide):

1. **Vector RAG**: A traditional semantic search RAG using FAISS embeddings.
2. **GraphRAG**: A knowledge-graph based approach utilizing Neo4j and Cypher query generation.

## 🏗️ Architecture

### Vector RAG
- **PDF Loader**: PyMuPDF (`fitz`)
- **Chunking**: RecursiveCharacterTextSplitter (chunk size: 1000, overlap: 200)
- **Embeddings**: `sentence-transformers/all-mpnet-base-v2` (Local HuggingFace model)
- **Vector Store**: FAISS
- **Generator LLM**: Gemini 1.5 Flash (via LangChain Google GenAI)

### Graph RAG
- **Extractor LLM (Text)**: `nousresearch/hermes-3-llama-3.1-405b` (via OpenRouter)
- **Vision Extractor (Images)**: `qwen/qwen2.5-vl-72b-instruct` (via OpenRouter)
- **Graph Store**: Neo4j AuraDB Cloud
- **Cypher Generator & QA Model**: `meta-llama/llama-3.1-70b-instruct` (via OpenRouter)
- **Cypher Logic**: Uses `GraphCypherQAChain` to auto-generate Cypher queries and traverse relationships.

## 📂 Project Structure

```text
GraphRAG/
├── config/              # Pydantic Settings and centralized configuration
├── data/                # Source PDFs (ISO 20022)
├── evaluation/          # Ground truth dataset, Ragas metrics, and evaluator script
├── graph_rag/           # Knowledge Extractor, Neo4j Graph loader, and Cypher Retriever
├── streamlit_app/       # Interactive Web UI to compare both pipelines side-by-side
├── utils/               # LLM Factory and Matplotlib Visualizer
├── vector_rag/          # PyMuPDF loader, chunker, embeddings, FAISS store
├── .env                 # API Keys
├── requirements.txt     # Python dependencies
└── README.md            # You are here
```

## 🚀 How to Run

### 1. Setup Environment
Ensure your `.env` is configured correctly:
```env
GOOGLE_API_KEY=your_key
OPENROUTER_API_KEY=your_key
NEO4J_URI=neo4j+s://<db_id>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Run the Evaluation
The evaluation script uses the **Ragas framework** to calculate Faithfulness, Answer Relevancy, Context Precision, and Context Recall.
```bash
python evaluation/evaluator.py
```
This will test both pipelines against 5 ground-truth questions and save the results as `vector_rag_metrics.csv` and `graph_rag_metrics.csv`.

### 3. Launch the Streamlit App
The interactive web application provides a side-by-side chat interface and visualizes the evaluation metrics in a Radar Chart.
```bash
streamlit run streamlit_app/app.py
```

## 📊 Scientific Comparison & Metrics
*(Run the evaluator and launch the Streamlit App to view the live comparison charts!)*

Usually:
- **Vector RAG** excels at broad, semantic questions and fetching large conceptual chunks.
- **GraphRAG** excels at precise relationship questions (e.g., "Which organization owns X?"), avoiding hallucination by enforcing strict schema traversal.
