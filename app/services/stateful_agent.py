"""
Stateful Agent Service

Implements a LangGraph-compatible stateful conversational agent that tracks:
- Product profiles and classification state
- Multi-turn conversation context
- Classification history and confidence scores

This service provides the core agent logic without coupling to any specific LLM backend.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class GateDecision(str, Enum):
    """Security gate decisions."""
    ALLOW = "ALLOW"
    REDIRECT = "REDIRECT"
    BLOCK = "BLOCK"


class TurnAction(str, Enum):
    """Actions determined by turn analysis."""
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    CLASSIFY = "CLASSIFY"
    CALCULATE_DUTY = "CALCULATE_DUTY"
    SEARCH = "SEARCH"
    PARSE_DOCUMENT = "PARSE_DOCUMENT"
    GENERAL_QA = "GENERAL_QA"


@dataclass
class ProductProfile:
    """Holds product classification state."""
    name: str = ""
    description: str = ""
    hs_code: str = ""
    confidence: float = 0.0
    duty_rate: Optional[float] = None
    gst_rate: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TurnAnalysis:
    """Result of analyzing user input."""
    action: TurnAction
    confidence: float
    needs_clarification: bool
    suggested_clarification: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentState:
    """Complete state of the conversational agent."""
    session_id: str
    messages: list[dict] = field(default_factory=list)
    product_profile: ProductProfile = field(default_factory=ProductProfile)
    last_classification: Optional[dict] = None
    turn_analysis: Optional[TurnAnalysis] = None
    assistant_reply: str = ""
    document_context: Optional[dict] = None
    gate_decision: GateDecision = GateDecision.ALLOW
    uploaded_files: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DomainGatekeeper:
    """
    Security gatekeeper that checks if queries are within domain scope.
    Prevents off-topic, adversarial, and malicious inputs.
    """

    def __init__(
        self,
        domain_keywords: Optional[set[str]] = None,
        allowed_refusal_response: Optional[str] = None
    ):
        """
        Initialize domain gatekeeper.
        
        Args:
            domain_keywords: Set of keywords that indicate in-domain queries
            allowed_refusal_response: Response to send for out-of-domain queries
        """
        self.domain_keywords = domain_keywords or {
            "customs", "tariff", "hs", "code", "duty", "import", "export",
            "classification", "igst", "bcd", "invoice", "trade", "commerce",
            "shipping", "logistics", "dgft", "product", "valve", "motor",
            "machinery", "textile", "pharma", "chemical", "electronics"
        }
        
        self.allowed_refusal_response = allowed_refusal_response or (
            "I am a specialized **Indian Customs and ITC-HS Classification Assistant**. "
            "I can only assist with customs tariffs, HSN/ITC-HS codes, import/export duties, "
            "DGFT policies, and commercial invoice analysis.\n\n"
            "Please share a product description or customs-related question."
        )

    def check_query(self, query: str) -> tuple[GateDecision, Optional[str]]:
        """
        Check if query is in-domain.
        
        Args:
            query: User query text
        
        Returns:
            Tuple of (GateDecision, optional reason/response)
        """
        query_lower = query.lower()
        
        # Check for injection attacks
        dangerous_patterns = [
            r"(?:ignore|forget|override|system prompt|api key|internal)",
            r"(?:print|output|reveal|leak).{0,20}(?:prompt|key|secret)",
            r"(?:exec|eval|__import__|system\()",
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, query_lower):
                return GateDecision.BLOCK, "Security block: Potential injection attack detected."
        
        # Check if query contains domain keywords
        query_words = set(query_lower.split())
        common_words = {"the", "a", "is", "and", "or", "in", "of", "to", "for", "with"}
        domain_words = query_words - common_words
        
        keyword_matches = len(domain_words & self.domain_keywords)
        
        # Allow if sufficient keyword overlap or if it's a clarification
        if keyword_matches > 0 or len(query) < 30:
            return GateDecision.ALLOW, None
        
        # Redirect off-topic queries
        return GateDecision.REDIRECT, self.allowed_refusal_response


class TurnAnalyzer:
    """
    Analyzes user input to determine the appropriate agent action.
    """

    def __init__(self):
        self.action_patterns = {
            TurnAction.CLASSIFY: [
                r"(?:classify|what.*?code|what.*?hs|categorize)",
                r"(?:is|are) this (?:a|an|this)?",
            ],
            TurnAction.CALCULATE_DUTY: [
                r"(?:calculate|compute|duty|tariff|tax|rate)",
                r"(?:how much|what.*?charge|cost)",
            ],
            TurnAction.PARSE_DOCUMENT: [
                r"(?:upload|parse|read|extract|from).{0,30}(?:invoice|document|file|image)",
                r"(?:invoice|document|receipt|commercial)",
            ],
            TurnAction.SEARCH: [
                r"(?:current|latest|recent).{0,20}(?:rate|duty|tariff)",
                r"(?:what.*?rate|search for)",
            ],
            TurnAction.ASK_CLARIFICATION: [
                r"(?:what.*?mean|explain|details|more info)",
                r"(?:clarify|specify|describe)",
            ],
        }

    def analyze(
        self,
        query: str,
        product_profile: ProductProfile,
        message_count: int
    ) -> TurnAnalysis:
        """
        Analyze user query to determine action.
        
        Args:
            query: User query text
            product_profile: Current product profile state
            message_count: Number of messages in conversation
        
        Returns:
            TurnAnalysis with recommended action
        """
        query_lower = query.lower()
        scored_actions = {}
        
        # Score each action based on pattern matches
        for action, patterns in self.action_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    score += 1
            scored_actions[action] = score
        
        # Determine best action
        best_action = max(scored_actions, key=scored_actions.get)
        confidence = min(scored_actions[best_action] / 2.0, 1.0)
        
        # Check if clarification is needed
        needs_clarification = False
        clarification_msg = None
        
        if best_action == TurnAction.CALCULATE_DUTY and not product_profile.hs_code:
            needs_clarification = True
            clarification_msg = "I need to first classify the product. Could you provide more details about the item?"
        
        if best_action == TurnAction.PARSE_DOCUMENT and not any(query_lower.endswith(ext) for ext in [".pdf", ".png", ".jpg", ".jpeg"]):
            if "upload" in query_lower or "invoice" in query_lower:
                needs_clarification = True
                clarification_msg = "Could you please upload a document image or PDF?"
        
        return TurnAnalysis(
            action=best_action,
            confidence=confidence,
            needs_clarification=needs_clarification,
            suggested_clarification=clarification_msg,
            metadata={
                "pattern_scores": scored_actions,
                "product_state": {
                    "has_code": bool(product_profile.hs_code),
                    "confidence": product_profile.confidence,
                },
                "conversation_turns": message_count,
            }
        )


class MultimodalMessageParser:
    """
    Parses multimodal inputs: text queries and uploaded documents.
    Extracts semantic content from images using OCR or vision API.
    """

    def __init__(self):
        self.supported_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

    def parse_text_input(self, text: str) -> dict:
        """
        Parse and normalize text input.
        
        Args:
            text: User text input
        
        Returns:
            Parsed input dictionary
        """
        # Remove extra whitespace
        cleaned = " ".join(text.split())
        
        # Extract entities (HSN codes, quantities, values)
        hs_codes = re.findall(r"\b\d{2,8}\b", cleaned)
        
        # Extract monetary values
        values = re.findall(r"(?:USD|INR|Rs\.?|₹)\s*[\d,]+(?:\.\d{2})?", cleaned)
        
        # Extract quantities
        quantities = re.findall(r"(\d+)\s*(?:units?|pieces?|boxes?|kg|lbs)", cleaned, re.IGNORECASE)
        
        return {
            "original": text,
            "cleaned": cleaned,
            "extracted_codes": hs_codes,
            "extracted_values": values,
            "extracted_quantities": quantities,
            "character_count": len(cleaned),
            "word_count": len(cleaned.split()),
        }

    def parse_document_metadata(self, file_path: str) -> dict:
        """
        Extract metadata from uploaded document.
        
        Args:
            file_path: Path to uploaded file
        
        Returns:
            Document metadata dictionary
        """
        import os
        from pathlib import Path
        
        path = Path(file_path)
        ext = path.suffix.lower()
        
        if ext not in self.supported_extensions:
            raise ValueError(f"Unsupported file type: {ext}")
        
        return {
            "file_path": str(path),
            "file_name": path.name,
            "file_extension": ext,
            "file_size_bytes": os.path.getsize(file_path),
            "is_image": ext in {".png", ".jpg", ".jpeg", ".webp"},
            "is_pdf": ext == ".pdf",
        }

    def prepare_multimodal_input(
        self,
        text_query: str,
        file_paths: Optional[list[str]] = None
    ) -> dict:
        """
        Prepare combined multimodal input.
        
        Args:
            text_query: Text query from user
            file_paths: Optional list of file paths
        
        Returns:
            Multimodal input dictionary
        """
        result = {
            "text": self.parse_text_input(text_query),
            "documents": [],
        }
        
        if file_paths:
            for file_path in file_paths:
                try:
                    metadata = self.parse_document_metadata(file_path)
                    result["documents"].append(metadata)
                except ValueError as e:
                    result["documents"].append({
                        "file_path": file_path,
                        "error": str(e),
                    })
        
        return result


class StatefulAgent:
    """
    Main stateful agent that orchestrates multi-turn interactions.
    Maintains conversation state, product classification, and history.
    """

    def __init__(
        self,
        gatekeeper: Optional[DomainGatekeeper] = None,
        analyzer: Optional[TurnAnalyzer] = None,
        parser: Optional[MultimodalMessageParser] = None,
    ):
        """
        Initialize stateful agent.
        
        Args:
            gatekeeper: Domain security gatekeeper
            analyzer: Turn analyzer
            parser: Multimodal message parser
        """
        self.gatekeeper = gatekeeper or DomainGatekeeper()
        self.analyzer = analyzer or TurnAnalyzer()
        self.parser = parser or MultimodalMessageParser()
        
        # Callback hooks for external services
        self.on_classify: Optional[Callable[[str], dict]] = None
        self.on_search: Optional[Callable[[str], dict]] = None
        self.on_parse_document: Optional[Callable[[str], dict]] = None
        self.on_generate_response: Optional[Callable[[AgentState], str]] = None

    def process_turn(
        self,
        state: AgentState,
        user_message: str,
        file_paths: Optional[list[str]] = None,
    ) -> AgentState:
        """
        Process a single turn of conversation.
        
        Args:
            state: Current agent state
            user_message: User's message text
            file_paths: Optional uploaded files
        
        Returns:
            Updated agent state
        """
        # 1. Security gate
        gate_decision, gate_response = self.gatekeeper.check_query(user_message)
        state.gate_decision = gate_decision
        
        if gate_decision == GateDecision.BLOCK:
            state.assistant_reply = "I cannot process that request due to security constraints."
            return state
        
        if gate_decision == GateDecision.REDIRECT:
            state.assistant_reply = gate_response or self.gatekeeper.allowed_refusal_response
            return state
        
        # 2. Parse multimodal input
        parsed_input = self.parser.prepare_multimodal_input(user_message, file_paths)
        state.uploaded_files = file_paths or []
        
        # 3. Analyze turn to determine action
        turn_analysis = self.analyzer.analyze(
            user_message,
            state.product_profile,
            len(state.messages)
        )
        state.turn_analysis = turn_analysis
        
        # 4. Add user message to history
        state.messages.append({
            "role": "user",
            "content": user_message,
            "parsed_input": parsed_input,
            "timestamp": self._get_timestamp(),
        })
        
        # 5. Execute action based on analysis
        if turn_analysis.action == TurnAction.CLASSIFY and self.on_classify:
            classification = self.on_classify(user_message)
            if classification:
                state.product_profile.hs_code = classification.get("hs_code", "")
                state.product_profile.confidence = classification.get("confidence", 0.0)
                state.product_profile.duty_rate = classification.get("duty_rate")
                state.product_profile.gst_rate = classification.get("gst_rate")
                state.last_classification = classification
        
        elif turn_analysis.action == TurnAction.PARSE_DOCUMENT and self.on_parse_document:
            if file_paths:
                doc_data = self.on_parse_document(file_paths[0])
                state.document_context = doc_data
        
        elif turn_analysis.action == TurnAction.SEARCH and self.on_search:
            search_result = self.on_search(user_message)
            state.metadata["last_search"] = search_result
        
        # 6. Generate response
        if self.on_generate_response:
            state.assistant_reply = self.on_generate_response(state)
        else:
            # Default response
            if turn_analysis.needs_clarification and turn_analysis.suggested_clarification:
                state.assistant_reply = turn_analysis.suggested_clarification
            else:
                state.assistant_reply = f"Processing your {turn_analysis.action.value.lower()} request..."
        
        # 7. Add assistant reply to history
        state.messages.append({
            "role": "assistant",
            "content": state.assistant_reply,
            "turn_analysis": turn_analysis.metadata,
            "timestamp": self._get_timestamp(),
        })
        
        return state

    def _get_timestamp(self) -> str:
        """Get ISO format timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def reset_state(self, session_id: str) -> AgentState:
        """
        Create a fresh agent state.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Fresh AgentState
        """
        return AgentState(session_id=session_id)
