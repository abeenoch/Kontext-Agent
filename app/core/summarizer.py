import logging
from typing import Dict, Any, List, Optional
from groq import AsyncGroq

from app.config import settings

logger = logging.getLogger(__name__)


class Summarizer:
    """
    LLM-powered meeting summarizer using Groq API.
    """
    
    def __init__(self):
        # Check if API key is properly set
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "":
            logger.warning("GROQ_API_KEY not set - summarization will not work. Please add GROQ_API_KEY to your .env file")
            self.client = None
        else:
            self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL
    
    async def summarize_intermediate(self, transcript: str) -> str:
        """
        Generate intermediate summary (brief, for periodic updates).
        
        Args:
            transcript: Current meeting transcript
        
        Returns:
            Summary text
        """
        if not self.client:
            logger.warning("Skipping intermediate summary - Groq API not configured")
            return "Meeting in progress..."
        
        if not transcript or len(transcript) < 50:
            return "Meeting in progress..."
        
        prompt = f"""You are a meeting assistant. Provide a brief 2-3 sentence summary of this meeting so far.
Focus on the main topics being discussed and any important points mentioned.

Transcript:
{transcript[-2000:]}  

Brief summary:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a concise meeting summarizer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated intermediate summary: {len(summary)} chars")
            
            return summary
            
        except Exception as e:
            logger.error(f"Intermediate summarization error: {e}", exc_info=True)
            return "Summary generation unavailable."
    
    async def summarize_final(self, transcript: str) -> Dict[str, Any]:
        """
        Generate comprehensive final summary with structure.
        
        Args:
            transcript: Complete meeting transcript
        
        Returns:
            Structured summary dict
        """
        if not transcript or len(transcript) < 50:
            return {
                "overview": "No transcript available.",
                "key_points": [],
                "decisions": [],
                "action_items": []
            }
        
        if not self.client:
            logger.warning("Skipping final summary - Groq API not configured")
            return {
                "overview": "Summary generation not available - API key not configured.",
                "key_points": [],
                "decisions": [],
                "action_items": []
            }
        
        # Truncate transcript to avoid token limit (Groq free tier: 8000 TPM)
        # Roughly 1 token = 4 characters, so 8000 tokens ≈ 32k chars
        # Leave room for prompt overhead and response, use 20k char limit
        max_chars = 20000
        if len(transcript) > max_chars:
            logger.info(f"Truncating transcript from {len(transcript)} to {max_chars} chars for summarization")
            # Keep first 30% and last 70% to preserve context and recent discussion
            keep_first = max_chars // 3
            keep_last = (max_chars * 2) // 3
            truncated = transcript[:keep_first] + "\n[...middle section omitted...]\n" + transcript[-keep_last:]
            transcript = truncated
        
        prompt = f"""You are a professional meeting summarizer. Analyze this meeting transcript and provide a structured summary.

Transcript:
{transcript}

Provide your response in this exact JSON format:
{{
    "overview": "A 2-3 sentence high-level summary of the meeting",
    "key_points": ["point 1", "point 2", "point 3"],
    "decisions": ["decision 1", "decision 2"],
    "action_items": ["action 1", "action 2"]
}}

Ensure all fields are present, even if empty arrays. Be specific and actionable."""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional meeting summarizer. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            import json
            summary = json.loads(response.choices[0].message.content)
            
            # Validate structure
            required_keys = ["overview", "key_points", "decisions", "action_items"]
            for key in required_keys:
                if key not in summary:
                    summary[key] = [] if key != "overview" else "No summary available"
            
            logger.info(f"Generated final summary: {len(summary['key_points'])} key points, "
                       f"{len(summary['action_items'])} action items")
            
            return summary
            
        except Exception as e:
            logger.error(f"Final summarization error: {e}", exc_info=True)
            return {
                "overview": f"Summary generation failed: {str(e)[:100]}",
                "key_points": [],
                "decisions": [],
                "action_items": []
            }
    
    async def answer_question(self, question: str, context: str) -> str:
        """
        Answer a question about the meeting using context.
        
        Args:
            question: User's question
            context: Meeting transcript or relevant context
        
        Returns:
            Answer text
        """
        if not self.client:
            logger.warning("Cannot answer question - Groq API not configured")
            return "I'm sorry, the AI assistant is not configured. Please set up your GROQ_API_KEY in the .env file."
        
        prompt = f"""You are a helpful meeting assistant. Answer the user's question based on the meeting context provided.
If the answer isn't in the context, say so politely.

Meeting Context:
{context[-3000:]}

User Question: {question}

Answer:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful meeting assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.4
            )
            
            answer = response.choices[0].message.content.strip()
            logger.info(f"Answered question: {question[:50]}...")
            
            return answer
            
        except Exception as e:
            logger.error(f"Question answering error: {e}", exc_info=True)
            return "I'm sorry, I encountered an error processing your question."



summarizer = Summarizer()