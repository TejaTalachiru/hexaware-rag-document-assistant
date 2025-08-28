import logging
import re
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class QueryGuardrails:
    def __init__(self):
        # Define harmful content patterns
        self.harmfulPatterns = [
            r'\b(hack|crack|break|bypass|exploit)\b',
            r'\b(illegal|unlawful|criminal)\b',
            r'\b(violence|violent|harm|hurt|kill)\b',
            r'\b(drug|weapon|bomb|terrorist)\b',
            r'\b(porn|sexual|explicit)\b'
        ]
        
        # Define off-topic patterns (non-document related)
        self.offTopicPatterns = [
            r'\bweather\b',
            r'\bstock price\b',
            r'\bnews today\b',
            r'\bcurrent events\b',
            r'\bsports score\b'
        ]
        
        # Query optimization patterns
        self.stopWords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being'
        }
    
    def validate_query(self, query: str) -> Dict[str, Any]:
        """Validate user query against safety and content guidelines"""
        
        if not query or not query.strip():
            return {
                "isValid": False,
                "reason": "Query cannot be empty"
            }
        
        if len(query.strip()) < 3:
            return {
                "isValid": False,
                "reason": "Query too short. Please provide a more detailed question."
            }
        
        if len(query) > 500:
            return {
                "isValid": False,
                "reason": "Query too long. Please keep questions under 500 characters."
            }
        
        # Check for harmful content
        queryLower = query.lower()
        for harmfulPattern in self.harmfulPatterns:
            if re.search(harmfulPattern, queryLower, re.IGNORECASE):
                logger.warning(f"⚠️ Blocked harmful query pattern: {harmfulPattern}")
                return {
                    "isValid": False,
                    "reason": "Query contains inappropriate content. Please ask something else."
                }
        
        # Check for completely off-topic queries
        offTopicMatches = 0
        for offTopicPattern in self.offTopicPatterns:
            if re.search(offTopicPattern, queryLower, re.IGNORECASE):
                offTopicMatches += 1
        
        if offTopicMatches > 0:
            return {
                "isValid": False,
                "reason": "I can only answer questions about the uploaded documents. Please ask about the document content."
            }
        
        return {
            "isValid": True,
            "reason": "Query passed validation"
        }
    
    def optimize_query(self, query: str) -> str:
        """Optimize query for better retrieval performance"""
        
        # Clean and normalize
        cleanQuery = query.strip().lower()
        
        # Remove special characters except spaces and question marks
        cleanQuery = re.sub(r'[^\w\s\?]', ' ', cleanQuery)
        
        # Split into words
        queryWords = cleanQuery.split()
        
        # Remove stop words but keep question structure
        if not any(word in ['what', 'how', 'when', 'where', 'why', 'who'] for word in queryWords):
            # Only remove stop words if it's not a question
            optimizedWords = [word for word in queryWords if word not in self.stopWords and len(word) > 2]
        else:
            # Keep question words and important terms
            optimizedWords = [word for word in queryWords if len(word) > 1]
        
        # Rejoin and return
        optimizedQuery = ' '.join(optimizedWords)
        
        # Ensure minimum length
        if len(optimizedQuery) < len(query) * 0.3:
            return query
        
        logger.info(f"🔧 Query optimized: '{query}' -> '{optimizedQuery}'")
        return optimizedQuery
    
    def validate_generated_answer(self, generatedAnswer: str, retrievedContext: List[Dict[str, Any]]) -> str:
        """Validate and potentially modify generated answer"""
        
        if not generatedAnswer or not generatedAnswer.strip():
            return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."
        
        # Check if answer is grounded in context
        if not retrievedContext:
            if "I don't know" not in generatedAnswer and "don't have" not in generatedAnswer:
                return "I don't have enough information in the available documents to answer that question."
        
        # Check for harmful content in generated answer
        answerLower = generatedAnswer.lower()
        for harmfulPattern in self.harmfulPatterns:
            if re.search(harmfulPattern, answerLower, re.IGNORECASE):
                logger.warning(f"⚠️ Blocked harmful generated content")
                return "I cannot provide that information. Please ask about something else."
        
        # Ensure answer references sources when available
        if retrievedContext and "document" not in answerLower and "source" not in answerLower:
            contextSources = [ctx.get("documentTitle", "document") for ctx in retrievedContext[:2]]
            sourceText = f" (Based on: {', '.join(contextSources)})"
            return generatedAnswer + sourceText
        
        return generatedAnswer
    
    def is_query_about_documents(self, query: str) -> bool:
        """Check if query is asking about document content"""
        documentIndicators = [
            'document', 'pdf', 'file', 'paper', 'report', 'text', 'content',
            'what does', 'according to', 'mentioned', 'states', 'says'
        ]
        
        queryLower = query.lower()
        return any(indicator in queryLower for indicator in documentIndicators)
    
    def extract_query_intent(self, query: str) -> Dict[str, Any]:
        """Extract intent and key entities from query"""
        queryLower = query.lower()
        
        # Determine query type
        if any(word in queryLower for word in ['what', 'define', 'explain']):
            queryType = 'definition'
        elif any(word in queryLower for word in ['how', 'process', 'method']):
            queryType = 'procedure'
        elif any(word in queryLower for word in ['when', 'date', 'time']):
            queryType = 'temporal'
        elif any(word in queryLower for word in ['where', 'location', 'place']):
            queryType = 'location'
        elif any(word in queryLower for word in ['why', 'reason', 'because']):
            queryType = 'explanation'
        elif any(word in queryLower for word in ['who', 'person', 'people']):
            queryType = 'entity'
        else:
            queryType = 'general'
        
        return {
            "queryType": queryType,
            "isQuestion": '?' in query,
            "wordCount": len(query.split()),
            "extractedAt": datetime.utcnow().isoformat()
        }
