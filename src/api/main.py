from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import logging
import time, datetime
import httpx

from src.services.document_ingestion import GoogleDriveDocumentIngestion
from src.services.retrieval_service import RagRetrievalService
from src.config.settings import appSettings

# Configure logging
logging.basicConfig(level=appSettings.log_level)  # FIXED
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="RAG System API",
    description="Retrieval-Augmented Generation system with Elasticsearch and Open LLM",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
documentIngestionService = GoogleDriveDocumentIngestion()
retrievalService = RagRetrievalService()

# Pydantic models
class QueryRequest(BaseModel):
    query: str
    sessionId: Optional[str] = "default"
    searchMode: Optional[str] = "hybrid"
    maxResults: Optional[int] = 5

class QueryResponse(BaseModel):
    success: bool
    answer: str
    sources: List[Dict[str, str]]
    error: Optional[str] = None

class AuthRequest(BaseModel):
    authorizationCode: str
    credentialsJson: Optional[str] = None


@app.get("/healthz")
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check endpoint - performs real service verification"""
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "services": {},
        "system": {}
    }
    
    # Track overall health
    overall_healthy = True
    
    # 1. Check Elasticsearch Health
    try:
        es_client = documentIngestionService.elasticClient
        if es_client and es_client.elasticClient:
            # Ping Elasticsearch cluster
            es_ping = es_client.elasticClient.ping()
            
            # Get cluster health
            if es_ping:
                cluster_health = es_client.elasticClient.cluster.health()
                health_status["services"]["elasticsearch"] = {
                    "status": "up",
                    "cluster_status": cluster_health.get("status", "unknown"),
                    "nodes": cluster_health.get("number_of_nodes", 0),
                    "active_shards": cluster_health.get("active_shards", 0)
                }
            else:
                health_status["services"]["elasticsearch"] = {"status": "down", "error": "Ping failed"}
                overall_healthy = False
        else:
            health_status["services"]["elasticsearch"] = {"status": "down", "error": "Client not initialized"}
            overall_healthy = False
            
    except Exception as e:
        logger.error(f"❌ Elasticsearch health check failed: {e}")
        health_status["services"]["elasticsearch"] = {"status": "down", "error": str(e)}
        overall_healthy = False
    
    # 2. Check Ollama Server Health
    try:
        llm_client = retrievalService.llmClient
        ollama_url = llm_client.baseUrl if llm_client else appSettings.ollama_base_url
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if Ollama server is responding
            response = await client.get(ollama_url)
            
            if response.status_code == 200 and "ollama" in response.text.lower():
                # Check available models
                try:
                    models_response = await client.get(f"{ollama_url}/api/tags")
                    if models_response.status_code == 200:
                        models_data = models_response.json()
                        model_names = [model["name"] for model in models_data.get("models", [])]
                        
                        health_status["services"]["ollama"] = {
                            "status": "up",
                            "url": ollama_url,
                            "models_available": len(model_names),
                            "default_model": appSettings.default_llm_model,
                            "model_ready": appSettings.default_llm_model in model_names or "llama3:latest" in model_names
                        }
                    else:
                        health_status["services"]["ollama"] = {
                            "status": "partial",
                            "url": ollama_url,
                            "error": "Models API not responding"
                        }
                except Exception as model_error:
                    health_status["services"]["ollama"] = {
                        "status": "partial", 
                        "url": ollama_url,
                        "error": f"Model check failed: {model_error}"
                    }
            else:
                health_status["services"]["ollama"] = {
                    "status": "down",
                    "url": ollama_url,
                    "error": f"Server not responding (status: {response.status_code})"
                }
                overall_healthy = False
                
    except Exception as e:
        logger.error(f"❌ Ollama health check failed: {e}")
        health_status["services"]["ollama"] = {
            "status": "down",
            "url": appSettings.ollama_base_url,
            "error": str(e)
        }
        overall_healthy = False
    
    # 4. Check Retrieval Service Health
    try:
        # Get system statistics
        system_stats = retrievalService.get_system_stats()
        health_status["system"] = {
            "active_sessions": system_stats.get("active_sessions", 0),
            "cache_items": system_stats.get("cache_stats", {}).get("total_items", 0),
            "cache_hit_rate": system_stats.get("cache_stats", {}).get("hit_rate", 0.0),
            "reranker_available": system_stats.get("reranker_available", False)
        }
    except Exception as e:
        logger.error(f"❌ System stats check failed: {e}")
        health_status["system"] = {"error": str(e)}
    
    # 5. Set overall status
    if not overall_healthy:
        health_status["status"] = "degraded"
    
    # Check if any critical service is down
    critical_services = ["elasticsearch", "ollama"]
    critical_down = any(
        health_status["services"].get(service, {}).get("status") == "down" 
        for service in critical_services
    )
    
    if critical_down:
        health_status["status"] = "unhealthy"
    
    return health_status

@app.post("/auth/google-drive")
async def authenticate_google_drive(credentials_file: UploadFile = File(None)):
    """Initiate Google Drive authentication"""
    try:
        credentialsJson = None
        if credentials_file:
            credentialsContent = await credentials_file.read()
            credentialsJson = credentialsContent.decode('utf-8')
        
        authResult = documentIngestionService.authenticate_google_drive(credentialsJson)
        return authResult
        
    except Exception as authError:
        logger.error(f"❌ Authentication failed: {authError}")
        raise HTTPException(status_code=500, detail=str(authError))

@app.post("/auth/complete")
async def complete_authentication(auth_request: AuthRequest):
    """Complete Google Drive authentication"""
    try:
        result = documentIngestionService.complete_authentication(
            auth_request.authorizationCode,
            auth_request.credentialsJson
        )
        return result
        
    except Exception as authError:
        logger.error(f"❌ Authentication completion failed: {authError}")
        raise HTTPException(status_code=500, detail=str(authError))

@app.post("/ingest")
async def ingest_documents(folder_id: Optional[str] = None):
    """Ingest documents from Google Drive"""
    try:
        ingestionResult = documentIngestionService.ingest_documents_from_drive(folder_id)
        return ingestionResult
        
    except Exception as ingestionError:
        logger.error(f"❌ Document ingestion failed: {ingestionError}")
        raise HTTPException(status_code=500, detail=str(ingestionError))

@app.post("/query", response_model=QueryResponse)
async def process_query(query_request: QueryRequest):
    """Process user query through RAG pipeline"""
    try:
        result = retrievalService.process_query(
            userQuery=query_request.query,
            sessionId=query_request.sessionId,
            searchMode=query_request.searchMode,
            maxResults=query_request.maxResults
        )
        
        return QueryResponse(
            success=result["success"],
            answer=result["answer"],
            sources=result.get("sources", []),
            error=result.get("error")
        )
        
    except Exception as queryError:
        logger.error(f"❌ Query processing failed: {queryError}")
        raise HTTPException(status_code=500, detail=str(queryError))


@app.get("/list-pdfs")
async def list_drive_pdfs(folder_id: Optional[str] = None):
    """List PDF files in Google Drive"""
    try:
        result = documentIngestionService.list_drive_pdfs(folder_id)
        return result
        
    except Exception as listError:
        logger.error(f"❌ Failed to list PDFs: {listError}")
        raise HTTPException(status_code=500, detail=str(listError))

@app.get("/status")
async def get_system_status():
    """Get system status and statistics"""
    try:
        ingestionStatus = documentIngestionService.get_ingestion_status()
        activeSessions = retrievalService.get_active_sessions()
        
        return {
            "ingestion": ingestionStatus,
            "activeChatSessions": len(activeSessions),
            "systemHealthy": True
        }
        
    except Exception as statusError:
        logger.error(f"❌ Status check failed: {statusError}")
        return {
            "error": str(statusError),
            "systemHealthy": False
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=appSettings.application_port)  # FIXED
