import logging
import requests
import json
from typing import Dict, List, Any, Optional
import time

from src.config.settings import appSettings

logger = logging.getLogger(__name__)

class OllamaLlmClient:
    def __init__(self):
        self.baseUrl = appSettings.ollama_base_url  # FIXED
        self.defaultModel = appSettings.default_llm_model  # FIXED
        self.defaultModel = 'llama3:latest'
        self.verify_connection()
    
    def verify_connection(self) -> bool:
        """Verify Ollama server is running and model is available"""
        try:
            # Check server health
            healthResponse = requests.get(f"{self.baseUrl}/api/tags", timeout=10)
            if healthResponse.status_code == 200:
                availableModels = healthResponse.json().get("models", [])
                modelNames = [model["name"] for model in availableModels]
                
                if self.defaultModel in modelNames:
                    logger.info(f"✅ Ollama connected, model {self.defaultModel} available")
                    return True
                else:
                    logger.warning(f"⚠️ Model {self.defaultModel} not found. Available: {modelNames}")
                    return False
            else:
                logger.error(f"❌ Ollama server returned status {healthResponse.status_code}")
                return False
                
        except requests.exceptions.RequestException as connectionError:
            logger.error(f"❌ Failed to connect to Ollama: {connectionError}")
            return False
        except Exception as generalError:
            logger.error(f"❌ Unexpected error verifying Ollama: {generalError}")
            return False
    
    def generate_answer(
        self, 
        userQuery: str, 
        retrievedContext: List[Dict[str, Any]], 
        chatHistory: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Generate answer using retrieved context and chat history"""
        
        try:
            # Build context from retrieved documents
            contextText = self._build_context_text(retrievedContext)
            
            # Build conversation history
            conversationHistory = self._build_conversation_history(chatHistory or [])
            
            # Create system prompt
            systemPrompt = self._create_system_prompt()
            
            # Create user prompt with context
            userPrompt = self._create_user_prompt(userQuery, contextText, conversationHistory)
            
            # Generate response
            generationResponse = self._call_ollama_api(systemPrompt, userPrompt)
            
            if generationResponse["success"]:
                return {
                    "success": True,
                    "answer": generationResponse["answer"],
                    "sources": self._extract_sources(retrievedContext),
                    "contextUsed": len(retrievedContext) > 0
                }
            else:
                return {
                    "success": False,
                    "error": generationResponse["error"],
                    "answer": "I apologize, but I'm unable to generate an answer right now. Please try again."
                }
                
        except Exception as generationError:
            logger.error(f"❌ Answer generation failed: {generationError}")
            return {
                "success": False,
                "error": str(generationError),
                "answer": "I apologize, but I encountered an error while generating the answer."
            }
    
    def _build_context_text(self, retrievedContext: List[Dict[str, Any]]) -> str:
        """Build formatted context text from retrieved documents"""
        if not retrievedContext:
            return ""
        
        contextParts = []
        for index, contextItem in enumerate(retrievedContext, 1):
            contextSection = f"""
Document {index}: {contextItem.get('documentTitle', 'Unknown')}
Source: {contextItem.get('fileName', 'Unknown')}
Content: {contextItem.get('content', '')}
---
"""
            contextParts.append(contextSection.strip())
        
        return "\n\n".join(contextParts)
    
    def _build_conversation_history(self, chatHistory: List[Dict[str, str]]) -> str:
        """Build conversation history for context"""
        if not chatHistory:
            return ""
        
        historyParts = []
        for messageEntry in chatHistory[-5:]:  # Last 5 messages for context
            role = messageEntry.get("role", "user")
            content = messageEntry.get("content", "")
            historyParts.append(f"{role.title()}: {content}")
        
        return "\n".join(historyParts)
    
    def _create_system_prompt(self) -> str:
        """Create comprehensive system prompt for the LLM"""
        return """You are a helpful AI assistant that answers questions based on provided document context. 

IMPORTANT GUIDELINES:
1. Base your answers ONLY on the provided context documents
2. If the context doesn't contain enough information to answer the question, say "I don't know" or "I don't have enough information"
3. Always cite your sources by mentioning the document name
4. Provide clear, concise, and accurate answers
5. If asked about something not in the context, politely explain that you can only answer based on the provided documents
6. Maintain a helpful and professional tone
7. If the question is unsafe, harmful, or inappropriate, refuse to answer and explain why

Remember: Your knowledge is limited to the provided context documents. Do not use external knowledge or make assumptions."""

    def _create_user_prompt(self, userQuery: str, contextText: str, conversationHistory: str) -> str:
        """Create user prompt with query, context, and history"""
        promptTemplate = f"""
{conversationHistory and f"Previous Conversation:\n{conversationHistory}\n\n" or ""}

Context Documents:
{contextText or "No relevant documents found."}

Current Question: {userQuery}

Please provide a helpful answer based on the context documents above. If the context doesn't contain relevant information, please say so clearly.
"""
        return promptTemplate.strip()
    
    def _call_ollama_api(self, systemPrompt: str, userPrompt: str) -> Dict[str, Any]:
        """Optimized API call with better timeout and performance settings"""
        max_retries = 3
        timeout_seconds = 180  # Increased to 3 minutes
        
        for attempt in range(max_retries):
            try:
                # Optimized request payload for faster responses
                requestPayload = {
                    "model": "llama3:latest",  # Use correct model name
                    "messages": [
                        {"role": "system", "content": systemPrompt},
                        {"role": "user", "content": userPrompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_ctx": 2048,      # Reduced context for speed
                        "num_predict": 300,   # Limit response length
                        "num_thread": 8,      # Use multiple CPU threads
                        "repeat_penalty": 1.1,
                        "top_k": 40
                    },
                    "keep_alive": "5m"  # Keep model loaded
                }
                
                print(f"🤔 Generating answer (attempt {attempt + 1}/{max_retries})...")
                start_time = time.time()
                
                apiResponse = requests.post(
                    f"{self.baseUrl}/api/chat",
                    json=requestPayload,
                    timeout=timeout_seconds
                )
                
                end_time = time.time()
                response_time = round(end_time - start_time, 2)
                
                if apiResponse.status_code == 200:
                    responseData = apiResponse.json()
                    generatedAnswer = responseData["message"]["content"]
                    
                    logger.info(f"✅ Answer generated in {response_time}s")
                    return {
                        "success": True,
                        "answer": generatedAnswer
                    }
                else:
                    logger.error(f"❌ Ollama API returned status {apiResponse.status_code}")
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 Retrying... (attempt {attempt + 2}/{max_retries})")
                        time.sleep(5)  # Wait before retry
                        continue
                    
                    return {
                        "success": False,
                        "error": f"API call failed with status {apiResponse.status_code}"
                    }
                    
            except requests.exceptions.Timeout:
                logger.error(f"❌ Timeout after {timeout_seconds}s (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    logger.info("🔄 Retrying with fresh connection...")
                    time.sleep(10)  # Longer wait for timeout recovery
                    continue
                
                return {
                    "success": False,
                    "error": f"Request timed out after {max_retries} attempts"
                }
            except Exception as apiError:
                logger.error(f"❌ Ollama API error: {apiError}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return {
                    "success": False,
                    "error": str(apiError)
                }
        
        return {
            "success": False,
            "error": "Max retries exceeded"
        }

    
    def _extract_sources(self, retrievedContext: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract source information for citations"""
        sourcesList = []
        for contextItem in retrievedContext:
            sourceInfo = {
                "title": contextItem.get("documentTitle", "Unknown Document"),
                "filename": contextItem.get("fileName", "Unknown File"),
                "url": contextItem.get("documentUrl", "#"),
                "snippet": contextItem.get("content", "")[:200] + "..."
            }
            sourcesList.append(sourceInfo)
        
        return sourcesList
