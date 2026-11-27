"""
Example: Integrating Stateful Agent into Existing RAG Pipeline

This module demonstrates how to plug the new services into your existing
FastAPI routes without modifying existing code.
"""

from typing import Optional
from app.services.chat_history_manager import ChatHistoryManager
from app.services.stateful_agent import StatefulAgent, GateDecision
from app.services.frontend_api import FrontendAPIService, SessionManager
from app.services.rag_service import RAGService


class IntegratedRAGAgent:
    """
    Bridges stateful agent with existing RAG service.
    Plugs into existing pipeline cleanly.
    """

    def __init__(
        self,
        rag_service: Optional[RAGService] = None,
        db_path: str = "chat_history.db",
    ):
        """
        Initialize integrated RAG agent.
        
        Args:
            rag_service: Existing RAG service instance
            db_path: Path to chat history database
        """
        # Create services
        self.stateful_agent = StatefulAgent()
        self.frontend_api = FrontendAPIService(
            stateful_agent=self.stateful_agent,
            db_path=db_path,
        )
        self.rag_service = rag_service
        
        # Wire up callbacks to integrate with RAG pipeline
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Setup callbacks to integrate with RAG service."""
        
        def classify_product(query: str) -> dict:
            """
            Use RAG service to classify product.
            Query the vector DB for similar products and their classifications.
            """
            if not self.rag_service:
                return {}
            
            try:
                # Query RAG for similar products
                response = self.rag_service.answer_query(
                    query=f"What is the HS code for: {query}",
                )
                
                # Parse response to extract HS code
                # This is a simplified version - adapt to your actual response format
                answer = response.answer if hasattr(response, 'answer') else str(response)
                
                return {
                    "hs_code": self._extract_hs_code(answer),
                    "product_description": query,
                    "confidence": 0.75,  # Adapt based on your confidence scoring
                    "source": "rag_pipeline",
                }
            except Exception as e:
                print(f"Classification error: {e}")
                return {}

        def parse_document(file_path: str) -> dict:
            """
            Parse uploaded document using RAG pipeline.
            Extract invoice data and product information.
            """
            # This is where you'd integrate document parsing
            # For now, return a placeholder
            return {
                "file_path": file_path,
                "extracted_text": "Document parsing not yet implemented",
                "items": [],
            }

        def search_tariff(query: str) -> dict:
            """
            Search for current tariff rates in RAG database.
            """
            if not self.rag_service:
                return {}
            
            try:
                response = self.rag_service.answer_query(
                    query=f"What is the current tariff rate for: {query}",
                )
                return {
                    "search_results": str(response),
                    "source": "rag_pipeline",
                }
            except Exception as e:
                print(f"Search error: {e}")
                return {}

        def generate_response(state) -> str:
            """
            Generate final response combining agent state with RAG results.
            """
            # Build context from state
            context = []
            
            if state.product_profile.hs_code:
                context.append(f"HS Code: {state.product_profile.hs_code}")
            
            if state.product_profile.duty_rate is not None:
                context.append(f"Basic Customs Duty: {state.product_profile.duty_rate}%")
            
            if state.turn_analysis and state.turn_analysis.suggested_clarification:
                return state.turn_analysis.suggested_clarification
            
            # Adapt response based on action
            if state.turn_analysis:
                action = state.turn_analysis.action.value
                if action == "CLASSIFY":
                    return f"I've classified the product as HS Code {state.product_profile.hs_code} with {state.product_profile.confidence:.0%} confidence."
                elif action == "CALCULATE_DUTY":
                    if state.product_profile.duty_rate:
                        return f"The Basic Customs Duty rate for HS Code {state.product_profile.hs_code} is {state.product_profile.duty_rate}%."
                    return "Please provide product details for duty calculation."
            
            return "How can I help you with customs classification?"

        # Register callbacks
        self.stateful_agent.on_classify = classify_product
        self.stateful_agent.on_parse_document = parse_document
        self.stateful_agent.on_search = search_tariff
        self.stateful_agent.on_generate_response = generate_response

    def _extract_hs_code(self, text: str) -> str:
        """Extract HS code from text using pattern matching."""
        import re
        # Look for 8-digit HS code
        match = re.search(r'\b(\d{8})\b', text)
        return match.group(1) if match else ""

    def process_message(
        self,
        session_id: str,
        message: str,
        file_paths: Optional[list[str]] = None,
    ) -> dict:
        """
        Process a message through integrated pipeline.
        
        Args:
            session_id: Session ID
            message: User message
            file_paths: Optional uploaded files
        
        Returns:
            Response with integrated RAG results
        """
        return self.frontend_api.send_chat_message(
            session_id=session_id,
            user_message=message,
            file_paths=file_paths,
        )

    def get_session(self, session_id: str) -> dict:
        """Get session state."""
        return self.frontend_api.get_saved_chat_session(session_id)

    def reload_session(self, session_id: str) -> dict:
        """Reload session from storage."""
        return self.frontend_api.reload_chat_history(session_id)

    def create_session(self, user_id: str = "default") -> str:
        """Create a new session."""
        response = self.frontend_api.start_new_session(f"{user_id}_{id(object())}")
        return response["session_id"]

    def clear_session(self, session_id: str) -> None:
        """Clear a session."""
        self.frontend_api.clear_session(session_id)


# Example usage
if __name__ == "__main__":
    # Initialize integrated agent
    # Note: This would use your actual RAG service instance
    integrated_agent = IntegratedRAGAgent(rag_service=None)
    
    # Create a session
    session_id = integrated_agent.create_session(user_id="test_user")
    print(f"Created session: {session_id}")
    
    # Send first message
    response1 = integrated_agent.process_message(
        session_id,
        "Classify a 2-inch industrial stainless steel ball valve"
    )
    print(f"\nAgent: {response1['reply']}")
    print(f"HS Code: {response1['active_product_profile'].get('hs_code', 'Not yet classified')}")
    
    # Follow-up question
    response2 = integrated_agent.process_message(
        session_id,
        "What's the duty rate and calculate total duty for 100 units at USD 2000 CIF?"
    )
    print(f"\nAgent: {response2['reply']}")
    
    # Reload session to verify persistence
    reloaded = integrated_agent.reload_session(session_id)
    print(f"\n\nReloaded session:")
    print(f"Total messages: {len(reloaded['messages'])}")
    print(f"Has classification: {reloaded['state']['product_profile'].get('hs_code') is not None}")
