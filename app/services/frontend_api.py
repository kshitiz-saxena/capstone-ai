"""
Frontend Integration API Service

Provides HTTP-compatible interface for frontend applications.
Handles chat message processing, session management, and history reloading.
Can be plugged into the FastAPI routes without modifying existing services.
"""

import re
from typing import Any, Optional
from dataclasses import asdict

from app.services.chat_history_manager import ChatHistoryManager
from app.services.stateful_agent import (
    StatefulAgent,
    AgentState,
    GateDecision,
)


class FrontendAPIService:
    """
    High-level API service for frontend integration.
    Bridges stateful agent and chat history persistence.
    """

    def __init__(
        self,
        stateful_agent: Optional[StatefulAgent] = None,
        history_manager: Optional[ChatHistoryManager] = None,
        db_path: str = "chat_history.db",
    ):
        """
        Initialize frontend API service.
        
        Args:
            stateful_agent: Stateful agent instance
            history_manager: Chat history manager instance
            db_path: Path to chat history database
        """
        self.agent = stateful_agent or StatefulAgent()
        self.history = history_manager or ChatHistoryManager(db_path)
        
        # In-memory cache of active sessions
        self._active_sessions: dict[str, AgentState] = {}

    def sanitize_session_id(self, session_id: str, max_length: int = 64) -> str:
        """
        Sanitize session ID to prevent SQL injection.
        
        Args:
            session_id: Raw session ID
            max_length: Maximum length after sanitization
        
        Returns:
            Safe session ID
        """
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(session_id))[:max_length]

    def send_chat_message(
        self,
        session_id: str,
        user_message: str,
        file_paths: Optional[list[str]] = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Process a chat message from frontend.
        
        Args:
            session_id: Session identifier
            user_message: User's message text
            file_paths: Optional uploaded file paths
            **kwargs: Additional parameters
        
        Returns:
            Response dictionary with reply and state info
        """
        # Sanitize inputs
        safe_session_id = self.sanitize_session_id(session_id)
        safe_message = self._sanitize_message(user_message)
        
        print(f"Received message for session {safe_session_id}: {safe_message}")
        
        # Validate message length
        if len(safe_message) > 4000:
            return {
                "thread_id": safe_session_id,
                "reply": "Message is too long. Please keep it under 4000 characters.",
                "error": "MESSAGE_TOO_LONG",
                "blocked_by_harness": True,
            }
        
        # Validate file count
        if file_paths and len(file_paths) > 2:
            return {
                "thread_id": safe_session_id,
                "reply": "You can upload a maximum of 2 files per message.",
                "error": "TOO_MANY_FILES",
                "blocked_by_harness": True,
            }
        
        # Load or create session state
        if safe_session_id not in self._active_sessions:
            self._load_session(safe_session_id)
        
        state = self._active_sessions[safe_session_id]
        
        # Process turn through agent
        updated_state = self.agent.process_turn(state, safe_message, file_paths)
        self._active_sessions[safe_session_id] = updated_state
        
        # Persist to history
        self.history.add_message(
            safe_session_id,
            role="user",
            content=safe_message,
            metadata={"files": file_paths}
        )
        
        self.history.add_message(
            safe_session_id,
            role="assistant",
            content=updated_state.assistant_reply,
            metadata={
                "action": updated_state.turn_analysis.action.value if updated_state.turn_analysis else None,
                "confidence": updated_state.turn_analysis.confidence if updated_state.turn_analysis else None,
            }
        )
        
        print(f"Updated state for session {safe_session_id}: {updated_state}")
        
        # Update product profile if changed
        if updated_state.product_profile.hs_code:
            self.history.update_product_profile(
                safe_session_id,
                product_name=updated_state.product_profile.name,
                description=updated_state.product_profile.description,
                hs_code=updated_state.product_profile.hs_code,
                confidence=updated_state.product_profile.confidence,
            )
        
        # Build response
        return {
            "thread_id": safe_session_id,
            "reply": updated_state.assistant_reply,
            "active_product_profile": {
                "hs_code": updated_state.product_profile.hs_code,
                "product_name": updated_state.product_profile.name,
                "confidence": updated_state.product_profile.confidence,
                "duty_rate": updated_state.product_profile.duty_rate,
                "gst_rate": updated_state.product_profile.gst_rate,
            },
            "classification": updated_state.last_classification,
            "document_context": updated_state.document_context,
            "needs_clarification": (
                updated_state.turn_analysis.needs_clarification
                if updated_state.turn_analysis else False
            ),
            "blocked_by_harness": updated_state.gate_decision != GateDecision.ALLOW,
            "turn_summary": {
                "action": updated_state.turn_analysis.action.value if updated_state.turn_analysis else None,
                "confidence": updated_state.turn_analysis.confidence if updated_state.turn_analysis else None,
            }
        }

    def get_saved_chat_session(self, session_id: str) -> dict[str, Any]:
        """
        Retrieve a complete saved chat session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Complete session data
        """
        safe_session_id = self.sanitize_session_id(session_id)
        
        # Get from database
        summary = self.history.get_session_summary(safe_session_id)
        
        return {
            "session_id": safe_session_id,
            "messages": summary["messages"],
            "product_profile": summary["product_profile"],
            "latest_classification": summary["latest_classification"],
            "conversation_length": len(summary["messages"]),
            "last_active": (
                summary["messages"][-1].get("created_at")
                if summary["messages"] else None
            ),
        }

    def reload_chat_history(self, session_id: str) -> dict[str, Any]:
        """
        Reload chat history and restore session state.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session state with full history
        """
        safe_session_id = self.sanitize_session_id(session_id)
        
        # Load from persistence
        self._load_session(safe_session_id)
        state = self._active_sessions[safe_session_id]
        
        # Get conversation history
        messages = self.history.get_conversation_history(safe_session_id)
        profile = self.history.get_product_profile(safe_session_id)
        classification = self.history.get_latest_classification(safe_session_id)
        
        return {
            "session_id": safe_session_id,
            "state": {
                "product_profile": {
                    "hs_code": profile.get("hs_code") if profile else None,
                    "product_name": profile.get("product_name") if profile else None,
                    "confidence": profile.get("classification_confidence") if profile else 0.0,
                },
                "last_classification": classification,
            },
            "messages": messages,
            "ready_to_continue": True,
        }

    def start_new_session(self, session_id: str, metadata: Optional[dict] = None) -> dict[str, Any]:
        """
        Initialize a new chat session.
        
        Args:
            session_id: Session identifier
            metadata: Optional session metadata
        
        Returns:
            New session information
        """
        safe_session_id = self.sanitize_session_id(session_id)
        
        # Create in database
        self.history.create_session(safe_session_id, metadata)
        
        # Create in-memory state
        new_state = self.agent.reset_state(safe_session_id)
        self._active_sessions[safe_session_id] = new_state
        
        return {
            "session_id": safe_session_id,
            "created": True,
            "ready": True,
            "initial_message": "Welcome to the Customs Classification Assistant. Please describe your product or upload an invoice.",
        }

    def get_session_analytics(self, session_id: str) -> dict[str, Any]:
        """
        Get analytics for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session analytics
        """
        safe_session_id = self.sanitize_session_id(session_id)
        summary = self.history.get_session_summary(safe_session_id)
        
        messages = summary["messages"]
        profile = summary["product_profile"]
        
        # Calculate statistics
        user_turns = len([m for m in messages if m["role"] == "user"])
        total_turns = len(messages) // 2
        
        return {
            "session_id": safe_session_id,
            "total_messages": len(messages),
            "user_turns": user_turns,
            "conversation_turns": total_turns,
            "has_classification": bool(profile),
            "classifications_attempted": self._count_classifications(safe_session_id),
            "files_uploaded": self._count_uploaded_files(safe_session_id),
        }

    def clear_session(self, session_id: str) -> dict[str, Any]:
        """
        Clear a session from both memory and storage.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Confirmation
        """
        safe_session_id = self.sanitize_session_id(session_id)
        
        # Clear memory
        if safe_session_id in self._active_sessions:
            del self._active_sessions[safe_session_id]
        
        # Clear database
        self.history.clear_session(safe_session_id)
        
        return {
            "session_id": safe_session_id,
            "cleared": True,
            "message": f"Session {safe_session_id} has been cleared.",
        }

    def _load_session(self, session_id: str) -> None:
        """Load session from storage into memory."""
        summary = self.history.get_session_summary(session_id)
        
        # Create new state
        state = self.agent.reset_state(session_id)
        
        # Restore from summary
        if summary["product_profile"]:
            profile = summary["product_profile"]
            state.product_profile.name = profile.get("product_name", "")
            state.product_profile.description = profile.get("description", "")
            state.product_profile.hs_code = profile.get("hs_code", "")
            state.product_profile.confidence = profile.get("classification_confidence", 0.0)
        
        if summary["latest_classification"]:
            state.last_classification = summary["latest_classification"]
        
        # Restore messages
        state.messages = summary["messages"]
        
        self._active_sessions[session_id] = state

    def _sanitize_message(self, message: str, max_length: int = 4000) -> str:
        """Remove potentially dangerous content from message."""
        # Remove control characters
        message = "".join(char for char in message if ord(char) >= 32 or char in "\n\r\t")
        
        # Truncate if needed
        return message[:max_length].strip()

    def _count_classifications(self, session_id: str) -> int:
        """Count number of classifications in session history."""
        # Simplified - return 0 for now
        # This would need direct DB access implementation
        return 0

    def _count_uploaded_files(self, session_id: str) -> int:
        """Count number of uploaded files in session."""
        messages = self.history.get_conversation_history(session_id)
        count = 0
        for msg in messages:
            metadata = msg.get("metadata", {})
            if metadata.get("files"):
                count += len(metadata["files"])
        return count


class SessionManager:
    """
    Manages multiple concurrent sessions with simplified API.
    Useful for multi-user scenarios.
    """

    def __init__(self, frontend_api: Optional[FrontendAPIService] = None):
        """
        Initialize session manager.
        
        Args:
            frontend_api: Frontend API service instance
        """
        self.api = frontend_api or FrontendAPIService()
        self._sessions: set[str] = set()

    def list_active_sessions(self) -> list[str]:
        """Get list of active sessions."""
        return list(self._sessions)

    def create_session(self, user_id: str, metadata: Optional[dict] = None) -> str:
        """
        Create a new session for a user.
        
        Args:
            user_id: User identifier
            metadata: Optional metadata
        
        Returns:
            Session ID
        """
        import uuid
        session_id = f"{user_id}_{uuid.uuid4().hex[:8]}"
        
        self.api.start_new_session(session_id, metadata)
        self._sessions.add(session_id)
        
        return session_id

    def end_session(self, session_id: str) -> None:
        """
        End a session.
        
        Args:
            session_id: Session identifier
        """
        self.api.clear_session(session_id)
        self._sessions.discard(session_id)
