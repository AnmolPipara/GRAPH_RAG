import json
import os
import time
from typing import List, Dict

from config.settings import settings
from vector_rag.pipeline import VectorRAGPipeline
from graph_rag.retriever import GraphRAGRetriever
from evaluation.metrics import evaluate_results

def load_questions() -> List[Dict]:
    path = os.path.join(os.path.dirname(__file__), 'questions.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def evaluate_vector_rag(questions: List[Dict]) -> List[Dict]:
    print("Evaluating Vector RAG...")
    # Initialize pipeline
    # The faiss index should already exist from previous ingestions
    try:
        pipeline = VectorRAGPipeline()
    except Exception as e:
        print(f"Failed to initialize Vector RAG: {e}")
        return []

    results = []
    for idx, q_data in enumerate(questions):
        print(f"Processing question {idx+1}/{len(questions)} for Vector RAG...")
        question = q_data['question']
        ground_truth = q_data['ground_truth']
        
        try:
            # invoke QA chain
            ans = pipeline.qa_chain.invoke(question)
            
            # extract context
            # In VectorRAGPipeline, we set return_source_documents=True
            # ans["source_documents"] contains the list of documents
            source_docs = ans.get('source_documents', [])
            contexts = [doc.page_content for doc in source_docs]
            
            results.append({
                "question": question,
                "answer": ans.get('result', ''),
                "contexts": contexts,
                "ground_truth": ground_truth
            })
        except Exception as e:
            print(f"Error on question {idx+1}: {e}")
            
    return results

def evaluate_graph_rag(questions: List[Dict]) -> List[Dict]:
    print("Evaluating Graph RAG...")
    try:
        retriever = GraphRAGRetriever()
    except Exception as e:
        print(f"Failed to initialize Graph RAG: {e}")
        return []

    results = []
    for idx, q_data in enumerate(questions):
        print(f"Processing question {idx+1}/{len(questions)} for Graph RAG...")
        question = q_data['question']
        ground_truth = q_data['ground_truth']
        
        try:
            ans = retriever.query(question)
            
            results.append({
                "question": question,
                "answer": ans.get('answer', ''),
                "contexts": ans.get('context', []),
                "ground_truth": ground_truth
            })
        except Exception as e:
            print(f"Error on question {idx+1}: {e}")
            
    return results

def main():
    questions = load_questions()
    if not questions:
        print("No questions found.")
        return
        
    print(f"Loaded {len(questions)} evaluation questions.")
    
    # 1. Evaluate Vector RAG
    vector_results = evaluate_vector_rag(questions)
    
    # 2. Evaluate Graph RAG
    graph_results = evaluate_graph_rag(questions)
    
    # 3. Calculate Metrics
    if vector_results:
        print("\nCalculating metrics for Vector RAG...")
        vector_df = evaluate_results(vector_results)
        print("\n=== Vector RAG Metrics ===")
        print(vector_df.mean(numeric_only=True))
        vector_df.to_csv("evaluation/vector_rag_metrics.csv", index=False)
        
    if graph_results:
        print("\nCalculating metrics for Graph RAG...")
        graph_df = evaluate_results(graph_results)
        print("\n=== Graph RAG Metrics ===")
        print(graph_df.mean(numeric_only=True))
        graph_df.to_csv("evaluation/graph_rag_metrics.csv", index=False)
        
    print("\nEvaluation complete. Detailed results saved to evaluation/ directory.")

if __name__ == "__main__":
    main()
