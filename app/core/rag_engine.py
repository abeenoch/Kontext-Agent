import logging
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
import hashlib
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    RAG engine for meeting context retrieval.
    Uses Pinecone vector database and sentence transformers.
    """
    
    def __init__(self):
        self.pc: Optional[Pinecone] = None
        self.index = None
        self.embedding_model = None
        self.index_name = "meeting-agent"
        self.initialized = False
    
    async def initialize(self):
        """Initialize Pinecone and embedding model."""
        if self.initialized:
            return
        
        if not settings.PINECONE_API_KEY:
            logger.warning("Pinecone API key not configured - RAG disabled")
            return
        
        try:
            logger.info("Initializing RAG engine...")
            
            # Initialize Pinecone
            self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in existing_indexes]
            
            if self.index_name not in index_names:
                logger.info(f"Creating Pinecone index: {self.index_name}")
                
                #
                self.pc.create_index(
                    name=self.index_name,
                    dimension=384,  # 
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region='us-east-1'  
                    )
                )
                logger.info("Index created successfully")
            
            # Connect to index
            self.index = self.pc.Index(self.index_name)
            
            # Initialize embedding model
            logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            self.initialized = True
            logger.info("RAG engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG engine: {e}", exc_info=True)
            logger.warning("RAG functionality disabled - will use fallback")
            self.initialized = False
    
    async def index_meeting(
        self, 
        meeting_id: str, 
        transcript: str, 
        summary: Dict[str, Any]
    ):
        """Index meeting content into Pinecone."""
        if not self.initialized:
            await self.initialize()
        
        if not self.initialized:
            logger.warning("RAG not initialized, skipping indexing")
            return
        
        try:
            # Split transcript into chunks
            chunks = self._chunk_text(transcript, chunk_size=500)
            
            # Create vectors
            vectors = []
            for i, chunk in enumerate(chunks):
                chunk_id = f"{meeting_id}-chunk-{i}"
                embedding = self.embedding_model.encode(chunk).tolist()
                
                metadata = {
                    "meeting_id": meeting_id,
                    "chunk_index": i,
                    "text": chunk[:1000],  # Store first 1000 chars
                    "type": "transcript"
                }
                
                vectors.append({
                    "id": chunk_id,
                    "values": embedding,
                    "metadata": metadata
                })
            
            # Index summary as well
            summary_text = self._summary_to_text(summary)
            summary_embedding = self.embedding_model.encode(summary_text).tolist()
            
            vectors.append({
                "id": f"{meeting_id}-summary",
                "values": summary_embedding,
                "metadata": {
                    "meeting_id": meeting_id,
                    "text": summary_text[:1000],
                    "type": "summary"
                }
            })
            
            # Upsert to Pinecone
            self.index.upsert(vectors=vectors, namespace=meeting_id)
            
            logger.info(f"Indexed {len(vectors)} vectors for meeting {meeting_id}")
            
        except Exception as e:
            logger.error(f"Failed to index meeting {meeting_id}: {e}", exc_info=True)
    
    async def query_meeting_context(
        self, 
        meeting_id: str, 
        query: str, 
        top_k: int = 3
    ) -> str:
        """Query meeting context based on user question."""
        if not self.initialized:
            await self.initialize()
        
        if not self.initialized:
            logger.warning("RAG not initialized, returning empty context")
            return ""
        
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Search in meeting namespace
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=meeting_id,
                include_metadata=True
            )
            
            # Extract relevant text
            context_parts = []
            for match in results.matches:
                if match.score > 0.5:  # Only include relevant matches
                    context_parts.append(match.metadata.get("text", ""))
            
            context = "\n\n".join(context_parts)
            logger.info(f"Retrieved {len(context_parts)} context chunks for query")
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to query context: {e}", exc_info=True)
            return ""
    
    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split text into chunks."""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
        
        return chunks
    
    def _summary_to_text(self, summary: Dict[str, Any]) -> str:
        """Convert summary dict to text."""
        parts = []
        
        if summary.get("overview"):
            parts.append(f"Overview: {summary['overview']}")
        
        if summary.get("key_points"):
            parts.append("Key Points: " + "; ".join(summary["key_points"]))
        
        if summary.get("decisions"):
            parts.append("Decisions: " + "; ".join(summary["decisions"]))
        
        if summary.get("action_items"):
            parts.append("Action Items: " + "; ".join(summary["action_items"]))
        
        return "\n".join(parts)



rag_engine = RAGEngine()