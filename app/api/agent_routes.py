"""
FastAPI Route Integration Guide

This module shows how to integrate the modular agent services
into your existing FastAPI application.

Add these routes to app/api/routes.py without modifying existing code.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
import os

# Import new services
from app.services.frontend_api import FrontendAPIService, SessionManager
from app.services.integrated_rag_agent import IntegratedRAGAgent

# Initialize services (do this once at app startup)
# In your main.py: api_service = FrontendAPIService()
# This should be a singleton instance

# ============================================================================
# Data Models for API Requests/Responses
# ============================================================================

class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    thread_id: str = Field(..., description="Session/thread ID")
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    files: Optional[List[str]] = Field(None, description="Uploaded file paths")


class ProductProfile(BaseModel):
    """Product classification state."""
    hs_code: Optional[str] = None
    product_name: Optional[str] = None
    confidence: float = 0.0
    duty_rate: Optional[float] = None
    gst_rate: Optional[float] = None


class ChatMessageResponse(BaseModel):
    """Response from chat endpoint."""
    thread_id: str
    reply: str
    active_product_profile: ProductProfile
    classification: Optional[dict] = None
    document_context: Optional[dict] = None
    needs_clarification: bool = False
    blocked_by_harness: bool = False
    turn_summary: Optional[dict] = None


class SessionSummary(BaseModel):
    """Summary of a chat session."""
    session_id: str
    conversation_length: int
    product_profile: Optional[dict] = None
    latest_classification: Optional[dict] = None
    last_active: Optional[str] = None


class SessionCreateRequest(BaseModel):
    """Request to create a new session."""
    user_id: Optional[str] = None
    metadata: Optional[dict] = None


class SessionCreateResponse(BaseModel):
    """Response when creating a session."""
    session_id: str
    created: bool
    ready: bool
    initial_message: str


# ============================================================================
# FastAPI Routes for Agent Services
# ============================================================================

def create_agent_routes(
    frontend_api: Optional[FrontendAPIService] = None,
    db_path: str = "chat_history.db"
) -> APIRouter:
    """
    Create FastAPI router with agent service endpoints.
    
    Usage in main.py:
    ```python
    from app.api.agent_routes import create_agent_routes
    app.include_router(create_agent_routes(frontend_api))
    ```
    
    Args:
        frontend_api: Optional FrontendAPIService instance
        db_path: Path to chat history database
    
    Returns:
        APIRouter with all agent endpoints
    """
    
    # Initialize service if not provided
    if frontend_api is None:
        frontend_api = FrontendAPIService(db_path=db_path)
    
    router = APIRouter(prefix="/api/chat", tags=["Chat Agent"])
    
    # ========================================================================
    # Chat Endpoints
    # ========================================================================
    
    @router.post("/message", response_model=ChatMessageResponse)
    async def send_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
        """
        Send a chat message and get agent response.
        
        - Applies domain gating and input validation
        - Tracks multi-turn conversation state
        - Persists to chat history
        - Returns product profile and classification state
        
        Example:
        ```bash
        curl -X POST http://localhost:8000/api/chat/message \\
          -H "Content-Type: application/json" \\
          -d '{
            "thread_id": "user_123",
            "message": "Classify a stainless steel valve"
          }'
        ```
        """
        response = frontend_api.send_chat_message(
            session_id=request.thread_id,
            user_message=request.message,
            file_paths=request.files,
        )
        
        # Map to response model
        product_profile = ProductProfile(**response["active_product_profile"])
        
        return ChatMessageResponse(
            thread_id=response["thread_id"],
            reply=response["reply"],
            active_product_profile=product_profile,
            classification=response.get("classification"),
            document_context=response.get("document_context"),
            needs_clarification=response.get("needs_clarification", False),
            blocked_by_harness=response.get("blocked_by_harness", False),
            turn_summary=response.get("turn_summary"),
        )
    
    # ========================================================================
    # Session Management Endpoints
    # ========================================================================
    
    @router.post("/sessions", response_model=SessionCreateResponse)
    async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
        """
        Create a new chat session.
        
        Example:
        ```bash
        curl -X POST http://localhost:8000/api/chat/sessions \\
          -H "Content-Type: application/json" \\
          -d '{
            "user_id": "user_123",
            "metadata": {"source": "mobile_app"}
          }'
        ```
        """
        # Generate session ID if not provided
        import uuid
        session_id = f"{request.user_id or 'user'}_{uuid.uuid4().hex[:8]}"
        
        response = frontend_api.start_new_session(session_id, request.metadata)
        
        return SessionCreateResponse(
            session_id=response["session_id"],
            created=response["created"],
            ready=response["ready"],
            initial_message=response["initial_message"],
        )
    
    @router.get("/sessions/{thread_id}", response_model=SessionSummary)
    async def get_session(thread_id: str) -> SessionSummary:
        """
        Get a session summary with conversation history.
        
        Example:
        ```bash
        curl http://localhost:8000/api/chat/sessions/user_123_abc12345
        ```
        """
        session = frontend_api.get_saved_chat_session(thread_id)
        
        return SessionSummary(
            session_id=session["session_id"],
            conversation_length=session["conversation_length"],
            product_profile=session["product_profile"],
            latest_classification=session["latest_classification"],
            last_active=session["last_active"],
        )
    
    @router.post("/sessions/{thread_id}/reload")
    async def reload_session(thread_id: str) -> dict:
        """
        Reload session history (for resuming interrupted conversations).
        
        Returns full conversation state to restore client-side UI.
        
        Example:
        ```bash
        curl -X POST http://localhost:8000/api/chat/sessions/user_123_abc12345/reload
        ```
        """
        return frontend_api.reload_chat_history(thread_id)
    
    @router.delete("/sessions/{thread_id}")
    async def delete_session(thread_id: str) -> dict:
        """
        Delete/clear a session and all its data.
        
        Example:
        ```bash
        curl -X DELETE http://localhost:8000/api/chat/sessions/user_123_abc12345
        ```
        """
        result = frontend_api.clear_session(thread_id)
        return result
    
    # ========================================================================
    # Analytics Endpoints
    # ========================================================================
    
    @router.get("/sessions/{thread_id}/analytics")
    async def get_session_analytics(thread_id: str) -> dict:
        """
        Get analytics for a session.
        
        Returns metrics like message count, turns, classifications, etc.
        
        Example:
        ```bash
        curl http://localhost:8000/api/chat/sessions/user_123_abc12345/analytics
        ```
        """
        return frontend_api.get_session_analytics(thread_id)
    
    return router


# ============================================================================
# Example: Integration with Existing FastAPI App
# ============================================================================

"""
Step 1: Modify your main.py to include the new routes

```python
from fastapi import FastAPI
from app.api.agent_routes import create_agent_routes
from app.services.frontend_api import FrontendAPIService

app = FastAPI()

# Initialize agent service
frontend_api = FrontendAPIService(db_path="chat_history.db")

# Include agent routes
app.include_router(create_agent_routes(frontend_api))

# Your existing routes
from app.api.routes import router
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Step 2: Frontend/Client Code Example (JavaScript/TypeScript)

```javascript
// Initialize session
async function startSession(userId) {
  const response = await fetch('http://localhost:8000/api/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId })
  });
  const data = await response.json();
  return data.session_id;
}

// Send message
async function sendMessage(threadId, message) {
  const response = await fetch('http://localhost:8000/api/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      thread_id: threadId,
      message: message
    })
  });
  return response.json();
}

// Reload session
async function reloadSession(threadId) {
  const response = await fetch(`http://localhost:8000/api/chat/sessions/${threadId}/reload`, {
    method: 'POST'
  });
  return response.json();
}

// Usage
(async () => {
  // Create new session
  const sessionId = await startSession('user_123');
  console.log('Session created:', sessionId);
  
  // Send message
  const response1 = await sendMessage(sessionId, 'Classify a stainless steel valve');
  console.log('Agent:', response1.reply);
  
  // Send follow-up
  const response2 = await sendMessage(sessionId, 'What is the duty rate?');
  console.log('Agent:', response2.reply);
  console.log('HS Code:', response2.active_product_profile.hs_code);
})();
```

Step 3: Testing with curl

```bash
# Create session
SESSION_ID=$(curl -s -X POST http://localhost:8000/api/chat/sessions \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "test_user"}' | jq -r '.session_id')
echo "Session: $SESSION_ID"

# Send message
curl -X POST http://localhost:8000/api/chat/message \\
  -H "Content-Type: application/json" \\
  -d "{
    \"thread_id\": \"$SESSION_ID\",
    \"message\": \"Classify a 2-inch stainless steel ball valve\"
  }" | jq '.reply'

# Get session info
curl http://localhost:8000/api/chat/sessions/$SESSION_ID | jq '.'

# Reload session
curl -X POST http://localhost:8000/api/chat/sessions/$SESSION_ID/reload | jq '.messages'

# Get analytics
curl http://localhost:8000/api/chat/sessions/$SESSION_ID/analytics | jq '.'

# Delete session
curl -X DELETE http://localhost:8000/api/chat/sessions/$SESSION_ID | jq '.'
```
"""

# ============================================================================
# Optional: Using Integrated RAG Agent
# ============================================================================

def create_rag_integrated_routes(rag_service=None, db_path: str = "chat_history.db") -> APIRouter:
    """
    Create routes with integrated RAG service.
    
    This version automatically connects to your existing RAG pipeline.
    
    Usage:
    ```python
    from app.services.rag_service import RAGService
    from app.api.agent_routes import create_rag_integrated_routes
    
    rag_service = RAGService()
    app.include_router(create_rag_integrated_routes(rag_service))
    ```
    """
    integrated_agent = IntegratedRAGAgent(rag_service=rag_service, db_path=db_path)
    
    router = APIRouter(prefix="/api/rag-chat", tags=["RAG Chat Agent"])
    
    @router.post("/message", response_model=ChatMessageResponse)
    async def send_rag_message(request: ChatMessageRequest) -> ChatMessageResponse:
        """
        Send message through integrated RAG pipeline.
        
        Automatically uses your existing RAG service for:
        - Product classification
        - Tariff rate lookup
        - Document parsing
        """
        response = integrated_agent.process_message(
            session_id=request.thread_id,
            message=request.message,
            file_paths=request.files,
        )
        
        product_profile = ProductProfile(**response["active_product_profile"])
        
        return ChatMessageResponse(
            thread_id=response["thread_id"],
            reply=response["reply"],
            active_product_profile=product_profile,
            classification=response.get("classification"),
            document_context=response.get("document_context"),
            needs_clarification=response.get("needs_clarification", False),
            blocked_by_harness=response.get("blocked_by_harness", False),
            turn_summary=response.get("turn_summary"),
        )
    
    return router
