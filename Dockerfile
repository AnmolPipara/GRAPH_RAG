# Vector RAG vs GraphRAG — Streamlit app container
# Works on Hugging Face Spaces, Render, Railway, or any Docker host.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (caches the heavy layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app + runtime artifacts (FAISS indexes, evaluation summaries, source PDF)
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
