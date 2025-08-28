from pydantic_settings import BaseSettings, SettingsConfigDict

class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="allow", env_case_sensitive=False)

    elastic_search_url: str = "https://localhost:9200"
    elastic_search_index_name: str = "rag_documents_v1"
    elastic_search_username: str = "elastic"
    elastic_search_password: str = "NIC-W*Z0nK-t9xs*VBsc"
    elastic_search_cert_fingerprint: str = "a1438924448beae0bcd415fec881734e73425f5bb95ce13b7fb4ef506d87cba0"

    google_drive_credentials_path: str = "credentials.json"

    ollama_base_url: str = "http://localhost:11434"
    default_llm_model: str = "llama3"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    max_retrieval_results: int = 5
    chunk_size_tokens: int = 300
    chunk_overlap_tokens: int = 50

    application_port: int = 8000
    streamlit_port: int = 8501
    log_level: str = "INFO"
    max_query_length: int = 500

    hexaware_blue_color: str = "#1E88E5"
    hexaware_white_color: str = "#FFFFFF"
    hexaware_light_blue_color: str = "#E3F2FD"

appSettings = ApplicationSettings()
