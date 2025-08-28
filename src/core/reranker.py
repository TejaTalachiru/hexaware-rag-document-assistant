from typing import List, Dict, Any
import re
from sentence_transformers import CrossEncoder
import logging

logger = logging.getLogger(__name__)

class SimpleReranker:
    def __init__(self):
        # Use a lightweight cross-encoder for re-ranking
        try:
            self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-2-v2')
            self.enabled = True
        except:
            self.enabled = False
            logger.warning("⚠️ Re-ranker not available, skipping re-ranking")
    
    def rerank_results(self, query: str, results: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """Re-rank search results using cross-encoder"""
        if not self.enabled or len(results) <= 1:
            return results[:top_k]
        
        try:
            # Prepare pairs for cross-encoder
            pairs = [(query, result.get("content", "")) for result in results]
            
            # Get relevance scores
            scores = self.model.predict(pairs)
            
            # Add scores and sort
            for i, result in enumerate(results):
                result["rerank_score"] = float(scores[i])
            
            # Sort by re-rank score and return top_k
            reranked = sorted(results, key=lambda x: x.get("rerank_score", 0), reverse=True)
            
            logger.info(f"🔄 Re-ranked {len(results)} results, top score: {reranked[0].get('rerank_score', 0):.3f}")
            return reranked[:top_k]
            
        except Exception as e:
            logger.error(f"❌ Re-ranking failed: {e}")
            return results[:top_k]
