import logging
from typing import Dict, List, Any, Optional
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ConnectionError, NotFoundError
from sentence_transformers import SentenceTransformer

from src.config.settings import appSettings

logger = logging.getLogger(__name__)

class ElasticsearchRagClient:
    def __init__(self):
        self.elasticClient = None
        self.embeddingModel = None
        self.indexName = appSettings.elastic_search_index_name
        self.initialize_client()
        self.initialize_embedding_model()

    def initialize_client(self) -> bool:
        """Initialize Elasticsearch client with authentication"""
        try:
            # For secured Elasticsearch
            self.elasticClient = Elasticsearch(
                appSettings.elastic_search_url,
                basic_auth=(appSettings.elastic_search_username, appSettings.elastic_search_password),
                ca_certs=False,  # Disable CA verification for local development
                verify_certs=False,
                ssl_show_warn=False
            )

            # Test connection
            if self.elasticClient.ping():
                logger.info("✅ Elasticsearch connection established successfully")
                return True
            else:
                logger.error("❌ Failed to ping Elasticsearch")
                return False

        except ConnectionError as connectionError:
            logger.error(f"❌ Elasticsearch connection failed: {connectionError}")
            return False
        except Exception as generalError:
            logger.error(f"❌ Unexpected error initializing Elasticsearch: {generalError}")
            return False

    def initialize_embedding_model(self):
        """Initialize sentence transformer model for dense embeddings"""
        try:
            self.embeddingModel = SentenceTransformer(appSettings.embedding_model_name)
            logger.info(f"✅ Embedding model loaded: {appSettings.embedding_model_name}")
        except Exception as embeddingError:
            logger.error(f"❌ Failed to load embedding model: {embeddingError}")
            raise embeddingError

    def create_index_mapping(self) -> bool:
        """Create Elasticsearch index with proper mappings for hybrid search"""
        mappingConfiguration = {
            "mappings": {
                "properties": {
                    "documentTitle": {"type": "text", "analyzer": "standard"},
                    "documentContent": {"type": "text", "analyzer": "standard"},
                    "chunkContent": {"type": "text", "analyzer": "standard"},
                    "chunkId": {"type": "keyword"},
                    "documentUrl": {"type": "keyword"},
                    "fileName": {"type": "keyword"},
                    "chunkIndex": {"type": "integer"},
                    "createdTimestamp": {"type": "date"},
                    "denseEmbedding": {
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine"
                    },
                    "sparseEmbedding": {
                        "type": "sparse_vector"
                    },
                    "textExpansion": {
                        "type": "text_expansion"
                    }
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "standard": {
                            "type": "standard",
                            "stopwords": "_english_"
                        }
                    }
                }
            }
        }

        try:
            if self.elasticClient.indices.exists(index=self.indexName):
                logger.info(f"⚠️ Index {self.indexName} already exists")
                return True

            self.elasticClient.indices.create(
                index=self.indexName,
                body=mappingConfiguration
            )
            logger.info(f"✅ Created index: {self.indexName}")
            return True

        except Exception as indexCreationError:
            logger.error(f"❌ Failed to create index: {indexCreationError}")
            return False

    def index_document_chunks(self, documentChunks: List[Dict[str, Any]]) -> bool:
        """Index document chunks with dense and sparse embeddings"""
        try:
            indexingActions = []

            for chunkData in documentChunks:
                denseVector = self.embeddingModel.encode(
                    chunkData["chunkContent"]
                ).tolist()

                indexAction = {
                    "_index": self.indexName,
                    "_id": chunkData["chunkId"],
                    "_source": {
                        **chunkData,
                        "denseEmbedding": denseVector
                    }
                }
                indexingActions.append(indexAction)

            successCount, failureList = helpers.bulk(
                self.elasticClient,
                indexingActions,
                index=self.indexName,
                refresh=True
            )

            logger.info(f"✅ Indexed {successCount} document chunks")
            if failureList:
                logger.warning(f"⚠️ {len(failureList)} chunks failed to index")

            return True

        except Exception as indexingError:
            logger.error(f"❌ Failed to index document chunks: {indexingError}")
            return False

    def hybrid_search(
        self,
        queryText: str,
        topResults: int = None,
        searchMode: str = "hybrid"
    ) -> List[Dict[str, Any]]:

        if topResults is None:
            topResults = appSettings.max_retrieval_results

        try:
            if searchMode == "hybrid":
                searchQuery = self._build_hybrid_query(queryText)
            elif searchMode == "elser_only":
                searchQuery = self._build_elser_query(queryText)
            else:
                searchQuery = self._build_bm25_query(queryText)

            searchResponse = self.elasticClient.search(
                index=self.indexName,
                body={
                    "query": searchQuery,
                    "size": topResults,
                    "_source": [
                        "documentTitle", "chunkContent", "documentUrl", 
                        "fileName", "chunkIndex", "chunkId"
                    ]
                }
            )

            retrievedResults = []
            for hit in searchResponse["hits"]["hits"]:
                resultData = {
                    "score": hit["_score"],
                    "chunkId": hit["_source"]["chunkId"],
                    "content": hit["_source"]["chunkContent"],
                    "documentTitle": hit["_source"]["documentTitle"],
                    "documentUrl": hit["_source"]["documentUrl"],
                    "fileName": hit["_source"]["fileName"],
                    "chunkIndex": hit["_source"]["chunkIndex"]
                }
                retrievedResults.append(resultData)

            logger.info(f"✅ Retrieved {len(retrievedResults)} results for query")
            return retrievedResults

        except Exception as searchError:
            logger.error(f"❌ Search failed: {searchError}")
            return []

    def _build_hybrid_query(self, queryText: str) -> Dict[str, Any]:
        queryEmbedding = self.embeddingModel.encode(queryText).tolist()
        return {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": queryText,
                            "fields": ["chunkContent^2", "documentTitle^3"],
                            "type": "best_fields",
                            "boost": 1.0
                        }
                    },
                    {
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.queryVector, 'denseEmbedding') + 1.0",
                                "params": {"queryVector": queryEmbedding}
                            },
                            "boost": 2.0
                        }
                    }
                ]
            }
        }
    
    def _build_elser_query(self, queryText: str) -> Dict[str, Any]:
        return {
            "text_expansion": {
                "textExpansion": {
                    "model_id": ".elser_model_2",
                    "model_text": queryText
                }
            }
        }

    def _build_bm25_query(self, queryText: str) -> Dict[str, Any]:
        return {
            "multi_match": {
                "query": queryText,
                "fields": ["chunkContent^2", "documentTitle^3"],
                "type": "best_fields"
            }
        }

    def get_index_stats(self) -> Dict[str, Any]:
        try:
            statsResponse = self.elasticClient.indices.stats(index=self.indexName)
            documentCount = statsResponse["indices"][self.indexName]["total"]["docs"]["count"]
            indexSize = statsResponse["indices"][self.indexName]["total"]["store"]["size_in_bytes"]
            return {
                "documentCount": documentCount,
                "indexSizeBytes": indexSize,
                "indexName": self.indexName,
                "status": "healthy"
            }
        except Exception as statsError:
            logger.error(f"❌ Failed to get index stats: {statsError}")
            return {"status": "error", "error": str(statsError)}
