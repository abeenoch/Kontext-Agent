import logging
from typing import Dict, Any, Optional
from notion_client import AsyncClient
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class NotionService:
    """Service for pushing meeting summaries to Notion."""
    
    def __init__(self):
        self.api_key = settings.NOTION_API_KEY
        self.database_id = settings.NOTION_DATABASE_ID
        self.client = None if not self.api_key else AsyncClient(auth=self.api_key)
    
    async def push_summary(self, meeting_id: str, summary: Dict[str, Any], title: str = None) -> Optional[str]:
        """
        Push meeting summary to Notion database.
        
        Args:
            meeting_id: Meeting identifier
            summary: Structured summary
            title: Meeting title
        
        Returns:
            Notion page URL if successful
        """
        if not self.client or not self.database_id:
            logger.warning("Notion integration not configured")
            return None
        
        try:
            # Prepare page properties
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title or f"Meeting - {meeting_id}"
                            }
                        }
                    ]
                },
                "Meeting ID": {
                    "rich_text": [
                        {
                            "text": {
                                "content": meeting_id
                            }
                        }
                    ]
                },
                "Date": {
                    "date": {
                        "start": datetime.now().isoformat()
                    }
                }
            }
            
            # Prepare page content (blocks)
            children = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Overview"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary.get('overview', '')}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Key Points"}}]
                    }
                },
            ]
            
            # Add key points as bulleted list
            for point in summary.get('key_points', []):
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": point}}]
                    }
                })
            
            # Add decisions
            children.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Decisions"}}]
                    }
                }
            ])
            
            for decision in summary.get('decisions', []):
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": decision}}]
                    }
                })
            
            # Add action items
            children.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Action Items"}}]
                    }
                }
            ])
            
            for action in summary.get('action_items', []):
                children.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": action}}],
                        "checked": False
                    }
                })
            
            # Create page in database
            response = await self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children
            )
            
            page_url = response['url']
            logger.info(f"Created Notion page for {meeting_id}: {page_url}")
            
            return page_url
            
        except Exception as e:
            logger.error(f"Notion push error: {e}", exc_info=True)
            return None


notion_service = NotionService()