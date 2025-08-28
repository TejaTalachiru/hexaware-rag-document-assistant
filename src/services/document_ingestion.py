import logging
import os
import io
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import PyPDF2
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config.settings import appSettings
from src.core.elastic_client import ElasticsearchRagClient

logger = logging.getLogger(__name__)

class GoogleDriveDocumentIngestion:
    def __init__(self):
        self.elasticClient = ElasticsearchRagClient()
        self.googleDriveService = None
        self.isAuthenticated = False
        self.scopes = ['https://www.googleapis.com/auth/drive.readonly']
    
    def authenticate_google_drive(self, credentialsJson: str = None) -> Dict[str, Any]:
        """Authenticate with Google Drive API"""
        try:
            if credentialsJson:
                # Handle credentials from JSON string (for Streamlit upload)
                credentialsData = json.loads(credentialsJson)
                flow = Flow.from_client_config(credentialsData, self.scopes)
            else:
                # Handle credentials from file
                if not os.path.exists(appSettings.google_drive_credentials_path):
                    return {
                        "success": False,
                        "error": "Google Drive credentials file not found",
                        "requiresAuth": True
                    }
                
                flow = Flow.from_client_secrets_file(
                    appSettings.google_drive_credentials_path,
                    self.scopes
                )
            
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
            
            authUrl, _ = flow.authorization_url(prompt='consent')
            
            return {
                "success": True,
                "authUrl": authUrl,
                "requiresAuth": True,
                "message": "Please visit the authentication URL and provide the authorization code"
            }
            
        except Exception as authError:
            logger.error(f"❌ Google Drive authentication setup failed: {authError}")
            return {
                "success": False,
                "error": str(authError),
                "requiresAuth": True
            }
    
    def complete_authentication(self, authorizationCode: str, credentialsJson: str = None) -> Dict[str, Any]:
        """Complete Google Drive authentication with authorization code"""
        try:
            if credentialsJson:
                credentialsData = json.loads(credentialsJson)
                flow = Flow.from_client_config(credentialsData, self.scopes)
            else:
                flow = Flow.from_client_secrets_file(
                    appSettings.google_drive_credentials_path,
                    self.scopes
                )
            
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
            flow.fetch_token(code=authorizationCode)
            
            self.googleDriveService = build('drive', 'v3', credentials=flow.credentials)
            self.isAuthenticated = True
            
            logger.info("✅ Google Drive authentication completed successfully")
            return {
                "success": True,
                "message": "Google Drive authentication successful"
            }
            
        except Exception as authCompletionError:
            logger.error(f"❌ Failed to complete Google Drive authentication: {authCompletionError}")
            return {
                "success": False,
                "error": str(authCompletionError)
            }
    
    def list_drive_pdfs(self, folderId: str = None) -> Dict[str, Any]:
        """List PDF files in Google Drive folder"""
        if not self.isAuthenticated:
            return {
                "success": False,
                "error": "Google Drive not authenticated",
                "files": []
            }
        
        try:
            targetFolderId = folderId or ""
            
            if targetFolderId:
                searchQuery = f"'{targetFolderId}' in parents and mimeType='application/pdf' and trashed=false"
            else:
                searchQuery = "mimeType='application/pdf' and trashed=false"
            
            driveResults = self.googleDriveService.files().list(
                q=searchQuery,
                fields="files(id, name, size, modifiedTime, webViewLink)",
                pageSize=100
            ).execute()
            
            pdfFiles = driveResults.get('files', [])
            
            logger.info(f"✅ Found {len(pdfFiles)} PDF files in Google Drive")
            return {
                "success": True,
                "files": pdfFiles,
                "count": len(pdfFiles)
            }
            
        except HttpError as driveError:
            logger.error(f"❌ Google Drive API error: {driveError}")
            return {
                "success": False,
                "error": f"Google Drive API error: {driveError}",
                "files": []
            }
        except Exception as generalError:
            logger.error(f"❌ Failed to list Drive PDFs: {generalError}")
            return {
                "success": False,
                "error": str(generalError),
                "files": []
            }
    
    def ingest_documents_from_drive(self, folderId: str = None) -> Dict[str, Any]:
        """Ingest and process PDF documents from Google Drive"""
        if not self.isAuthenticated:
            return {
                "success": False,
                "error": "Google Drive not authenticated"
            }
        
        try:
            # List PDF files
            listResult = self.list_drive_pdfs(folderId)
            if not listResult["success"]:
                return listResult
            
            pdfFiles = listResult["files"]
            if not pdfFiles:
                return {
                    "success": True,
                    "message": "No PDF files found to ingest",
                    "processedCount": 0
                }
            
            # Process each PDF file
            processedDocuments = 0
            totalChunks = 0
            failedFiles = []
            
            for pdfFile in pdfFiles:
                try:
                    logger.info(f"📄 Processing: {pdfFile['name']}")
                    
                    # Download PDF content
                    fileContent = self._download_pdf_content(pdfFile['id'])
                    if not fileContent:
                        failedFiles.append(pdfFile['name'])
                        continue
                    
                    # Extract text from PDF
                    extractedText = self._extract_pdf_text(fileContent)
                    if not extractedText.strip():
                        logger.warning(f"⚠️ No text extracted from {pdfFile['name']}")
                        failedFiles.append(pdfFile['name'])
                        continue
                    
                    # Create document chunks
                    documentChunks = self._create_document_chunks(
                        extractedText, 
                        pdfFile
                    )
                    
                    # Index chunks in Elasticsearch
                    if self.elasticClient.index_document_chunks(documentChunks):
                        processedDocuments += 1
                        totalChunks += len(documentChunks)
                        logger.info(f"✅ Processed {pdfFile['name']}: {len(documentChunks)} chunks")
                    else:
                        failedFiles.append(pdfFile['name'])
                    
                except Exception as fileProcessingError:
                    logger.error(f"❌ Failed to process {pdfFile['name']}: {fileProcessingError}")
                    failedFiles.append(pdfFile['name'])
            
            return {
                "success": True,
                "message": f"Document ingestion completed",
                "processedCount": processedDocuments,
                "totalChunks": totalChunks,
                "failedFiles": failedFiles,
                "totalFiles": len(pdfFiles)
            }
            
        except Exception as ingestionError:
            logger.error(f"❌ Document ingestion failed: {ingestionError}")
            return {
                "success": False,
                "error": str(ingestionError)
            }
    
    def _download_pdf_content(self, fileId: str) -> Optional[bytes]:
        """Download PDF file content from Google Drive"""
        try:
            downloadRequest = self.googleDriveService.files().get_media(fileId=fileId)
            fileContent = downloadRequest.execute()
            return fileContent
        except Exception as downloadError:
            logger.error(f"❌ Failed to download file {fileId}: {downloadError}")
            return None
    
    def _extract_pdf_text(self, pdfContent: bytes) -> str:
        """Extract text content from PDF bytes"""
        try:
            pdfReader = PyPDF2.PdfReader(io.BytesIO(pdfContent))
            extractedText = ""
            
            for pageNum in range(len(pdfReader.pages)):
                page = pdfReader.pages[pageNum]
                pageText = page.extract_text()
                extractedText += pageText + "\n"
            
            return extractedText.strip()
            
        except Exception as extractionError:
            logger.error(f"❌ PDF text extraction failed: {extractionError}")
            return ""
    
    def _create_document_chunks(self, documentText: str, fileInfo: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split document text into chunks for indexing"""
        # Simple chunking by sentences and character count
        sentences = documentText.split('. ')
        chunks = []
        currentChunk = ""
        chunkIndex = 0
        
        for sentence in sentences:
            # Check if adding this sentence would exceed chunk size
            if len(currentChunk) + len(sentence) > appSettings.chunk_size_tokens * 4:
                if currentChunk.strip():
                    chunks.append(self._create_chunk_object(
                        currentChunk.strip(), 
                        fileInfo, 
                        chunkIndex
                    ))
                    chunkIndex += 1
                
                # Start new chunk with overlap
                currentChunk = sentence + '. '
            else:
                currentChunk += sentence + '. '
        
        # Add final chunk
        if currentChunk.strip():
            chunks.append(self._create_chunk_object(
                currentChunk.strip(), 
                fileInfo, 
                chunkIndex
            ))
        
        return chunks
    
    def _create_chunk_object(self, chunkText: str, fileInfo: Dict[str, Any], chunkIndex: int) -> Dict[str, Any]:
        """Create chunk object for indexing"""
        chunkId = f"{fileInfo['id']}_{chunkIndex}"
        
        return {
            "chunkId": chunkId,
            "chunkContent": chunkText,
            "chunkIndex": chunkIndex,
            "documentTitle": fileInfo.get('name', 'Unknown'),
            "fileName": fileInfo.get('name', 'Unknown'),
            "documentUrl": fileInfo.get('webViewLink', '#'),
            "fileId": fileInfo['id'],
            "createdTimestamp": datetime.utcnow().isoformat()
        }
    
    def get_ingestion_status(self) -> Dict[str, Any]:
        """Get current ingestion status and statistics"""
        try:
            elasticStats = self.elasticClient.get_index_stats()
            
            return {
                "isAuthenticated": self.isAuthenticated,
                "elasticsearchStatus": elasticStats.get("status", "unknown"),
                "documentCount": elasticStats.get("documentCount", 0),
                "indexSize": elasticStats.get("indexSizeBytes", 0),
                "indexName": elasticStats.get("indexName", "unknown")
            }
            
        except Exception as statusError:
            logger.error(f"❌ Failed to get ingestion status: {statusError}")
            return {
                "isAuthenticated": self.isAuthenticated,
                "error": str(statusError)
            }
