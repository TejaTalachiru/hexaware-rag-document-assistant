import streamlit as st
import requests
import json
from typing import Dict, Any
import time
from datetime import datetime
import os
import sys

# Page configuration
st.set_page_config(
    page_title="RAG Document Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Fix Python path issue
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# Now we can import from src
from src.config.settings import appSettings

# Hexaware color scheme
HEXAWARE_BLUE = appSettings.hexaware_blue_color
HEXAWARE_WHITE = appSettings.hexaware_white_color
HEXAWARE_LIGHT_BLUE = appSettings.hexaware_light_blue_color

# Custom CSS
st.markdown(f"""
<style>
    .main-header {{
        background: linear-gradient(90deg, {HEXAWARE_BLUE} 0%, #1976D2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }}
    
    .main-header h1 {{
        color: {HEXAWARE_WHITE};
        text-align: center;
        margin: 0;
        font-weight: 600;
    }}
    
    .status-card {{
        background: {HEXAWARE_LIGHT_BLUE};
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid {HEXAWARE_BLUE};
        margin: 1rem 0;
    }}
    
    .success-message {{
        background: #d4edda;
        color: #155724;
        padding: 0.75rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }}
    
    .error-message {{
        background: #f8d7da;
        color: #721c24;
        padding: 0.75rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
        margin: 1rem 0;
    }}
    
    .chat-message {{
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }}
    
    .user-message {{
        background: {HEXAWARE_LIGHT_BLUE};
        margin-left: 2rem;
    }}
    
    .assistant-message {{
        background: {HEXAWARE_WHITE};
        border: 1px solid #e0e0e0;
        margin-right: 2rem;
    }}
    
    .source-citation {{
        background: #f8f9fa;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 3px solid {HEXAWARE_BLUE};
        margin: 0.5rem 0;
        font-size: 0.9rem;
    }}
    
    .folder-card {{
        background: {HEXAWARE_WHITE};
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin: 0.5rem 0;
    }}
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{int(time.time())}"
if "google_authenticated" not in st.session_state:
    st.session_state.google_authenticated = False
if "documents_ingested" not in st.session_state:
    st.session_state.documents_ingested = False
if "available_pdfs" not in st.session_state:
    st.session_state.available_pdfs = []

# API Configuration
API_BASE_URL = "http://localhost:8000"

def make_api_request(endpoint: str, method: str = "GET", data: Dict = None, files: Dict = None) -> Dict[str, Any]:
    """Make API request with error handling"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        
        if method == "POST":
            if files:
                response = requests.post(url, files=files, data=data)
            else:
                response = requests.post(url, json=data)
        else:
            response = requests.get(url)
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as apiError:
        return {"success": False, "error": str(apiError)}
    except Exception as generalError:
        return {"success": False, "error": str(generalError)}

def check_credentials_exist():
    """Check if Google Drive credentials file exists"""
    credentials_path = appSettings.google_drive_credentials_path
    return os.path.exists(credentials_path)

def initiate_google_drive_auth():
    """Start Google Drive authentication process"""
    try:
        response = make_api_request("/auth/google-drive", "POST")
        return response
    except Exception as e:
        return {"success": False, "error": str(e)}

# Header
st.markdown("""
<div class="main-header">
    <h1>📚 RAG Document Assistant</h1>
    <p style="text-align: center; color: white; margin: 0.5rem 0 0 0;">
        Powered by Elasticsearch, Open Source LLM & Google Drive Integration
    </p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown(f"### 🔧 System Control Panel")
    
    # System Status
    with st.expander("📊 System Status", expanded=True):
        if st.button("🔄 Refresh Status", use_container_width=True):
            status_response = make_api_request("/status")
            if status_response.get("success", True):
                st.session_state.system_status = status_response
        
        if "system_status" in st.session_state:
            status = st.session_state.system_status
            ingestion_status = status.get("ingestion", {})
            
            st.metric("Documents Indexed", ingestion_status.get("documentCount", 0))
            st.metric("Active Chat Sessions", status.get("activeChatSessions", 0))
            
            if ingestion_status.get("isAuthenticated"):
                st.success("✅ Google Drive Connected")
                st.session_state.google_authenticated = True
            else:
                st.warning("⚠️ Google Drive Not Connected")
    
    # Search Configuration
    with st.expander("⚙️ Search Settings", expanded=False):
        search_mode = st.selectbox(
            "Search Mode",
            ["hybrid", "elser_only", "bm25"],
            index=0,
            help="Hybrid combines multiple search methods for better results"
        )
        
        max_results = st.slider("Max Results", 1, 10, 5)
        
        st.session_state.search_settings = {
            "searchMode": search_mode,
            "maxResults": max_results
        }

# Main Content Tabs
tab_setup, tab_chat = st.tabs(["🔗 Google Drive Setup", "💬 Chat Assistant"])

# Google Drive Setup Tab
with tab_setup:
    st.markdown("## 📁 Google Drive PDF Document Ingestion")
    
    # Check if credentials file exists
    credentials_exist = check_credentials_exist()
    
    if not credentials_exist:
        st.error(f"""
        ❌ **Google Drive Credentials Not Found**
        
        Please ensure you have placed your Google Drive API credentials file at:
        `{appSettings.google_drive_credentials_path}`
        
        **Steps to get credentials:**
        1. Go to [Google Cloud Console](https://console.cloud.google.com/)
        2. Enable Google Drive API
        3. Create OAuth 2.0 credentials (Desktop app)
        4. Download the JSON file and save it as `credentials.json` in your project root
        """)
    else:
        st.success(f"✅ Credentials file found: `{appSettings.google_drive_credentials_path}`")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("### 🔐 Authentication & PDF Ingestion")
            
            if not st.session_state.google_authenticated:
                if st.button("🔑 Connect to Google Drive", type="primary", use_container_width=True):
                    with st.spinner("Initiating Google Drive authentication..."):
                        auth_response = initiate_google_drive_auth()
                        
                        if auth_response.get("success"):
                            st.session_state.auth_url = auth_response.get("authUrl")
                            st.success("✅ Authentication URL generated!")
                        else:
                            st.error(f"❌ Authentication failed: {auth_response.get('error')}")
                
                # Show auth URL and code input if available
                if "auth_url" in st.session_state:
                    st.markdown("### 🌐 Complete Authentication")
                    st.info(f"""
                    **Please visit this URL to authenticate:**
                    
                    {st.session_state.auth_url}
                    
                    Copy the authorization code from the browser and paste it below.
                    """)
                    
                    auth_code = st.text_input(
                        "📝 Enter Authorization Code:",
                        placeholder="Paste the authorization code here...",
                        type="password"
                    )
                    
                    if auth_code and st.button("✅ Complete Authentication", use_container_width=True):
                        with st.spinner("Completing authentication..."):
                            completion_response = make_api_request(
                                "/auth/complete",
                                "POST",
                                data={"authorizationCode": auth_code}
                            )
                            
                            if completion_response.get("success"):
                                st.session_state.google_authenticated = True
                                st.success("✅ Google Drive authentication completed!")
                                st.rerun()
                            else:
                                st.error(f"❌ Authentication failed: {completion_response.get('error')}")
            
            else:
                # Already authenticated - show PDF ingestion options
                st.success("✅ Google Drive Connected Successfully!")
                
                st.markdown("### 📂 PDF Document Ingestion")
                
                # Folder ID input
                folder_id = st.text_input(
                    "📁 Google Drive Folder ID (Optional)",
                    placeholder="Leave empty to scan entire Drive for PDFs",
                    help="Get folder ID from Google Drive URL: https://drive.google.com/drive/folders/FOLDER_ID_HERE"
                )
                
                col_ingest1, col_ingest2 = st.columns([1, 1])
                
                with col_ingest1:
                    if st.button("👁️ Preview Available PDFs", use_container_width=True):
                        with st.spinner("Scanning Google Drive for PDF files..."):
                            # Add API endpoint to list files
                            list_response = make_api_request(
                                f"/list-pdfs?folder_id={folder_id}" if folder_id else "/list-pdfs",
                                "GET"
                            )
                            
                            if list_response.get("success"):
                                st.session_state.available_pdfs = list_response.get("files", [])
                                st.success(f"Found {len(st.session_state.available_pdfs)} PDF files")
                            else:
                                st.error(f"Failed to list PDFs: {list_response.get('error')}")
                
                with col_ingest2:
                    if st.button("📥 Ingest All PDFs", type="primary", use_container_width=True):
                        with st.spinner("Processing PDF documents... This may take several minutes."):
                            ingest_response = make_api_request(
                                "/ingest",
                                "POST",
                                data={"folder_id": folder_id} if folder_id else {}
                            )
                            
                            if ingest_response.get("success"):
                                st.session_state.documents_ingested = True
                                st.success(f"""
                                ✅ **Document Ingestion Completed!**
                                
                                📊 **Results:**
                                - **Processed:** {ingest_response.get('processedCount', 0)} documents
                                - **Total chunks:** {ingest_response.get('totalChunks', 0)}
                                - **Failed:** {len(ingest_response.get('failedFiles', []))} documents
                                """)
                                
                                if ingest_response.get('failedFiles'):
                                    st.warning(f"⚠️ **Failed files:** {', '.join(ingest_response['failedFiles'])}")
                            else:
                                st.error(f"❌ Ingestion failed: {ingest_response.get('error')}")
                
                # Show available PDFs if scanned
                if st.session_state.available_pdfs:
                    st.markdown("### 📋 Available PDF Files")
                    for idx, pdf_file in enumerate(st.session_state.available_pdfs[:10], 1):  # Show first 10
                        st.markdown(f"""
                        <div class="folder-card">
                            <strong>{idx}. {pdf_file.get('name', 'Unknown')}</strong><br>
                            <small>📅 Modified: {pdf_file.get('modifiedTime', 'Unknown')[:10]}</small><br>
                            <small>📏 Size: {round(int(pdf_file.get('size', 0)) / 1024 / 1024, 2) if pdf_file.get('size') else 'Unknown'} MB</small>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if len(st.session_state.available_pdfs) > 10:
                        st.info(f"... and {len(st.session_state.available_pdfs) - 10} more files")
        
        with col2:
            # Setup Progress
            st.markdown("### 📊 Setup Progress")
            
            if credentials_exist:
                st.success("✅ Credentials Ready")
            else:
                st.error("❌ Credentials Missing")
            
            if st.session_state.google_authenticated:
                st.success("✅ Google Drive Connected")
            else:
                st.warning("⚠️ Authentication Required")
            
            if st.session_state.documents_ingested:
                st.success("✅ Documents Processed")
            else:
                st.info("📄 Documents Pending")

# Chat Assistant Tab  
with tab_chat:
    if not st.session_state.google_authenticated:
        st.warning("⚠️ Please connect to Google Drive in the setup tab first.")
    elif not st.session_state.documents_ingested:
        st.warning("⚠️ Please ingest PDF documents from Google Drive before starting to chat.")
    else:
        st.markdown("## 💬 Chat with Your PDF Documents")
        
        # Chat interface
        chat_container = st.container()
        
        # Display chat history
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    st.markdown(f"""
                    <div class="chat-message user-message">
                        <strong>🙋 You:</strong><br>
                        {message["content"]}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>🤖 Assistant:</strong><br>
                        {message["content"]}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display sources if available
                    if "sources" in message and message["sources"]:
                        st.markdown("**📚 Sources:**")
                        for idx, source in enumerate(message["sources"], 1):
                            st.markdown(f"""
                            <div class="source-citation">
                                <strong>{idx}. {source.get('title', 'Unknown')}</strong><br>
                                <em>📄 File: {source.get('filename', 'Unknown')}</em><br>
                                💬 {source.get('snippet', '')[:150]}...
                            </div>
                            """, unsafe_allow_html=True)
        
        # Chat input
        with st.form("chat_form", clear_on_submit=True):
            col_input, col_send = st.columns([4, 1])
            
            with col_input:
                user_question = st.text_input(
                    "Ask a question about your PDF documents:",
                    placeholder="What are the main findings in the research papers?",
                    label_visibility="collapsed"
                )
            
            with col_send:
                submitted = st.form_submit_button("Send 📤", use_container_width=True)
            
            if submitted and user_question:
                # Add user message to chat
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_question,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Process query
                with st.spinner("🤔 Searching through your documents..."):
                    search_settings = st.session_state.get("search_settings", {})
                    
                    query_response = make_api_request(
                        "/query",
                        "POST",
                        data={
                            "query": user_question,
                            "sessionId": st.session_state.session_id,
                            "searchMode": search_settings.get("searchMode", "hybrid"),
                            "maxResults": search_settings.get("maxResults", 5)
                        }
                    )
                    
                    if query_response.get("success"):
                        assistant_message = {
                            "role": "assistant",
                            "content": query_response["answer"],
                            "sources": query_response.get("sources", []),
                            "timestamp": datetime.now().isoformat()
                        }
                        st.session_state.chat_history.append(assistant_message)
                    else:
                        error_message = {
                            "role": "assistant", 
                            "content": f"❌ I encountered an error: {query_response.get('error', 'Unknown error')}",
                            "timestamp": datetime.now().isoformat()
                        }
                        st.session_state.chat_history.append(error_message)
                
                st.rerun()
        
        # Chat controls
        st.markdown("---")
        col_clear, col_export = st.columns([1, 1])
        
        with col_clear:
            if st.button("🗑️ Clear Chat History", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
        
        with col_export:
            if st.session_state.chat_history and st.button("📥 Export Chat", use_container_width=True):
                chat_export = {
                    "session_id": st.session_state.session_id,
                    "exported_at": datetime.now().isoformat(),
                    "chat_history": st.session_state.chat_history
                }
                
                st.download_button(
                    "💾 Download Chat History",
                    data=json.dumps(chat_export, indent=2),
                    file_name=f"chat_history_{st.session_state.session_id}.json",
                    mime="application/json",
                    use_container_width=True
                )

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>🚀 <strong>RAG Document Assistant</strong> | Built with Elasticsearch, Langchain & Streamlit</p>
    <p>💡 <strong>Tip:</strong> Use specific questions for better results. Example: "What are the key findings in the research paper?"</p>
</div>
""", unsafe_allow_html=True)

# NOTE: Removed st.run() - this was causing the error!
# Streamlit apps should be run with: streamlit run src/ui/streamlit_app.py
