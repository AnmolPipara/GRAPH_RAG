import os
import json
import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from utils.llm_factory import LLMFactory

def evaluate_results(results_list: list) -> pd.DataFrame:
    """
    Evaluates a list of results using Ragas metrics.
    results_list should be a list of dicts with:
    - question
    - answer
    - contexts (list of strings)
    - ground_truth
    """
    # Convert to HuggingFace dataset
    data = {
        "question": [r["question"] for r in results_list],
        "answer": [r["answer"] for r in results_list],
        "contexts": [r["contexts"] for r in results_list],
        "ground_truth": [r["ground_truth"] for r in results_list],
    }
    dataset = Dataset.from_dict(data)
    
    # Initialize the LLM and Embeddings to use for evaluation
    # We use our factory to get the Gemini (or chosen) LLM
    eval_llm = LLMFactory.get_llm()
    
    # For Ragas, we also need embeddings for some metrics like answer_relevancy
    # If the user has Vector RAG configured, we can use that embedding model
    from langchain_huggingface import HuggingFaceEmbeddings
    from config.settings import settings
    
    eval_embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    
    # Note: latest Ragas uses a slightly different syntax for passing LLM
    # We will pass the LangChain wrappers directly
    print("Running Ragas Evaluation (this may take some time depending on API limits)...")
    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=eval_llm,
        embeddings=eval_embeddings
    )
    
    return result.to_pandas()
