import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from src.core.elastic_client import ElasticsearchRagClient
from src.core.llm_client import OllamaLlmClient
from src.core.reranker import SimpleReranker
from src.core.cache_manager import SimpleCacheManager
from src.services.guardrails import QueryGuardrails

logger = logging.getLogger(__name__)

class RagRetrievalService:
    def __init__(self):
        self.elasticClient = ElasticsearchRagClient()
        self.llmClient = OllamaLlmClient()
        self.guardrails = QueryGuardrails()
        self.reranker = SimpleReranker()  # NEW: Reranker integration
        self.cache = SimpleCacheManager()  # NEW: Cache integration
        self.chatSessions = {}  # In-memory chat session storage
    
    def process_query(
        self, 
        userQuery: str,
        sessionId: str = "default",
        searchMode: str = "hybrid",
        maxResults: int = 5,
        enableReranking: bool = True
    ) -> Dict[str, Any]:
        """Process user query through enhanced RAG pipeline with caching and reranking"""
        
        try:
            # Input validation
            if not userQuery or not userQuery.strip():
                return {
                    "success": False,
                    "error": "Empty query provided",
                    "answer": "Please provide a valid question.",
                    "sources": []
                }
            
            # Step 1: Check cache first
            cached_result = self.cache.get(userQuery, searchMode)
            if cached_result:
                logger.info("📦 Returning cached result")
                # Update cache hit statistics
                self.cache._hit_count = getattr(self.cache, '_hit_count', 0) + 1
                return cached_result
            
            # Update cache miss statistics
            self.cache._total_requests = getattr(self.cache, '_total_requests', 0) + 1
            
            # Step 2: Query validation and guardrails
            validationResult = self.guardrails.validate_query(userQuery)
            if not validationResult["isValid"]:
                return {
                    "success": False,
                    "error": validationResult["reason"],
                    "answer": "I cannot process this query due to content guidelines.",
                    "sources": []
                }
            
            # Step 3: Query optimization and rewriting
            optimizedQuery = self.guardrails.optimize_query(userQuery)
            
            # Step 4: Context-aware query enhancement
            chatHistory = self.chatSessions.get(sessionId, [])
            contextualQuery = self._enhance_query_with_context(optimizedQuery, chatHistory)
            
            logger.info(f"🔍 Processing query: '{contextualQuery}' (original: '{userQuery}')")
            
            # Step 5: Retrieve relevant documents (get more for reranking)
            retrievalResults = self.elasticClient.hybrid_search(
                queryText=contextualQuery,
                topResults=maxResults * 3 if enableReranking else maxResults,  # Get more docs for reranking
                searchMode=searchMode
            )
            
            if not retrievalResults:
                result = {
                    "success": True,
                    "answer": "I couldn't find any relevant information to answer your question. Please try rephrasing or ask about something else.",
                    "sources": [],
                    "contextUsed": False,
                    "searchMode": searchMode,
                    "retrievedCount": 0,
                    "sessionId": sessionId
                }
                # Cache negative results too
                self.cache.set(userQuery, searchMode, result)
                return result
            
            # Step 6: Re-rank results (NEW FEATURE!)
            if enableReranking and len(retrievalResults) > 1:
                logger.info(f"🔄 Re-ranking {len(retrievalResults)} results...")
                rankedResults = self.reranker.rerank_results(
                    query=contextualQuery,
                    results=retrievalResults,
                    top_k=maxResults
                )
                logger.info(f"✅ Re-ranking complete, using top {len(rankedResults)} results")
            else:
                # Simple scoring fallback
                rankedResults = self._simple_rerank_results(retrievalResults, contextualQuery)[:maxResults]
            
            # Step 7: Generate answer using LLM
            generationResult = self.llmClient.generate_answer(
                userQuery=userQuery,
                retrievedContext=rankedResults,
                chatHistory=chatHistory
            )
            
            # Step 8: Update chat session
            if generationResult.get("success"):
                self._update_chat_session(sessionId, userQuery, generationResult.get("answer", ""))
            
            # Step 9: Final guardrails check on generated answer
            if generationResult.get("success"):
                finalAnswer = self.guardrails.validate_generated_answer(
                    generationResult.get("answer", ""),
                    rankedResults
                )
                generationResult["answer"] = finalAnswer
            
            # Step 10: Prepare final result
            result = {
                "success": generationResult.get("success", False),
                "answer": generationResult.get("answer", "I apologize, but I encountered an error generating the answer."),
                "sources": generationResult.get("sources", []),
                "contextUsed": generationResult.get("contextUsed", False),
                "searchMode": searchMode,
                "retrievedCount": len(rankedResults),
                "sessionId": sessionId,
                "cached": False,
                "reranked": enableReranking and len(retrievalResults) > 1
            }
            
            # Step 11: Cache successful results
            if result["success"]:
                self.cache.set(userQuery, searchMode, result)
            
            return result
            
        except Exception as queryProcessingError:
            logger.error(f"❌ Query processing failed: {queryProcessingError}")
            return {
                "success": False,
                "error": str(queryProcessingError),
                "answer": "I apologize, but I encountered an error while processing your query. Please try again.",
                "sources": [],
                "searchMode": searchMode,
                "sessionId": sessionId
            }
    
    def _enhance_query_with_context(self, query: str, chatHistory: List[Dict[str, str]]) -> str:
        """Enhance query with chat context for better retrieval"""
        if not chatHistory:
            return query
        
        # Get last few messages for context
        recentMessages = chatHistory[-6:]  # Last 3 exchanges
        contextTerms = []
        
        for message in recentMessages:
            if message.get("role") == "user":
                # Extract key terms from previous user queries
                queryWords = message.get("content", "").split()
                contextTerms.extend([word for word in queryWords if len(word) > 3])
        
        # Add context terms to current query if they're relevant
        if contextTerms:
            uniqueContextTerms = list(set(contextTerms))[:3]  # Limit to 3 terms
            enhancedQuery = f"{query} {' '.join(uniqueContextTerms)}"
            return enhancedQuery
        
        return query
    
    def _simple_rerank_results(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Simple re-ranking fallback when advanced reranker is not available"""
        # For now, just sort by Elasticsearch score (already relevance-sorted)
        return sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    
    def _update_chat_session(self, sessionId: str, userQuery: str, assistantAnswer: str):
        """Update chat session history"""
        if sessionId not in self.chatSessions:
            self.chatSessions[sessionId] = []
        
        # Add user query
        self.chatSessions[sessionId].append({
            "role": "user",
            "content": userQuery,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Add assistant answer
        self.chatSessions[sessionId].append({
            "role": "assistant", 
            "content": assistantAnswer,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 20 messages to prevent memory bloat
        if len(self.chatSessions[sessionId]) > 20:
            self.chatSessions[sessionId] = self.chatSessions[sessionId][-20:]
    
    def get_chat_history(self, sessionId: str) -> List[Dict[str, str]]:
        """Get chat history for a session"""
        return self.chatSessions.get(sessionId, [])
    
    def clear_chat_session(self, sessionId: str) -> bool:
        """Clear chat history for a session"""
        if sessionId in self.chatSessions:
            del self.chatSessions[sessionId]
            logger.info(f"🧹 Cleared chat session: {sessionId}")
            return True
        return False
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active chat sessions"""
        return list(self.chatSessions.keys())
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return self.cache.get_stats()
    
    def clear_cache(self) -> bool:
        """Clear the query cache"""
        try:
            self.cache.cache.clear()
            logger.info("🧹 Cache cleared successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear cache: {e}")
            return False
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        try:
            return {
                "active_sessions": len(self.chatSessions),
                "total_chat_messages": sum(len(history) for history in self.chatSessions.values()),
                "cache_stats": self.get_cache_stats(),
                "reranker_available": self.reranker.enabled if hasattr(self.reranker, 'enabled') else True,
                "elasticsearch_healthy": self.elasticClient.elasticClient.ping() if self.elasticClient.elasticClient else False
            }
        except Exception as e:
            logger.error(f"❌ Failed to get system stats: {e}")
            return {"error": str(e)}
