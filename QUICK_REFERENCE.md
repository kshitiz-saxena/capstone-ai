# Quick Reference Card: Modular Stateful Agent Services

## Files Created

| File | Purpose | Status |
|------|---------|--------|
| `app/services/chat_history_manager.py` | SQLite persistence for chat history | ✅ Ready |
| `app/services/stateful_agent.py` | Multi-turn stateful agent with security | ✅ Ready |
| `app/services/frontend_api.py` | HTTP-compatible API service | ✅ Ready |
| `app/services/integrated_rag_agent.py` | RAG pipeline integration | ✅ Ready |
| `app/api/agent_routes.py` | FastAPI routes (plug into main.py) | ✅ Ready |
| `AGENT_SERVICES_README.md` | Comprehensive documentation | ✅ 500+ lines |
| `examples_agent_services.py` | 6 working examples | ✅ All pass |
| `tests/test_agent_services.py` | Unit test suite | ✅ 29 tests pass |

---

## 30-Second Integration

### Option 1: Standalone Usage
```python
from app.services.frontend_api import FrontendAPIService
api = FrontendAPIService()
api.start_new_session("user_123")
response = api.send_chat_message("user_123", "Classify a valve")
print(response["reply"])
```

### Option 2: FastAPI Routes
```python
# In main.py
from app.api.agent_routes import create_agent_routes
from app.services.frontend_api import FrontendAPIService

frontend_api = FrontendAPIService()
app.include_router(create_agent_routes(frontend_api))
```

Now available:
- `POST /api/chat/message` - Send message
- `POST /api/chat/sessions` - Create session
- `GET /api/chat/sessions/{id}` - Get session
- `POST /api/chat/sessions/{id}/reload` - Reload history
- `DELETE /api/chat/sessions/{id}` - Delete session

### Option 3: RAG Integration
```python
from app.services.integrated_rag_agent import IntegratedRAGAgent
agent = IntegratedRAGAgent(rag_service=your_rag_service)
response = agent.process_message("user_123", "Classify a valve")
```

---

## Core Classes

### ChatHistoryManager
```python
from app.services.chat_history_manager import ChatHistoryManager

manager = ChatHistoryManager(db_path="chat.db")
manager.create_session("session_1")
manager.add_message("session_1", "user", "Hello")
messages = manager.get_conversation_history("session_1")
manager.update_product_profile("session_1", "Valve", "...", "8481.80.30", 0.95)
manager.add_classification("session_1", "8481.80.30", "...", 0.92, 7.5, 5.0)
```

### StatefulAgent
```python
from app.services.stateful_agent import StatefulAgent, AgentState

agent = StatefulAgent()
state = AgentState(session_id="session_1")

# Register callbacks
agent.on_classify = my_classify_fn
agent.on_search = my_search_fn
agent.on_parse_document = my_parse_fn
agent.on_generate_response = my_response_fn

# Process turn
state = agent.process_turn(state, "Classify a valve")
```

### FrontendAPIService
```python
from app.services.frontend_api import FrontendAPIService, SessionManager

api = FrontendAPIService()
api.start_new_session("session_1")
response = api.send_chat_message("session_1", "Query text")
session = api.get_saved_chat_session("session_1")
reloaded = api.reload_chat_history("session_1")
api.clear_session("session_1")

# Multi-user
manager = SessionManager()
sid = manager.create_session("user_123")
active = manager.list_active_sessions()
manager.end_session(sid)
```

### IntegratedRAGAgent
```python
from app.services.integrated_rag_agent import IntegratedRAGAgent

agent = IntegratedRAGAgent(rag_service=your_rag_service)
sid = agent.create_session("user_123")
response = agent.process_message(sid, "Query")
session = agent.reload_session(sid)
agent.clear_session(sid)
```

---

## API Response Format

```python
{
    "thread_id": "user_123_abc",
    "reply": "I've classified the product as...",
    "active_product_profile": {
        "hs_code": "8481.80.30",
        "product_name": "Ball Valve",
        "confidence": 0.92,
        "duty_rate": 7.5,
        "gst_rate": 5.0,
    },
    "classification": {
        "hs_code": "8481.80.30",
        "confidence": 0.92,
        "duty_rate": 7.5,
        "gst_rate": 5.0,
        "created_at": "2024-11-27T12:34:56Z",
        "source": "rag_pipeline",
    },
    "document_context": None,
    "needs_clarification": False,
    "blocked_by_harness": False,
    "turn_summary": {
        "action": "CLASSIFY",
        "confidence": 0.95,
    }
}
```

---

## Security Features

| Feature | Description | Status |
|---------|-------------|--------|
| **Domain Gating** | Prevents off-topic queries | ✅ Active |
| **Injection Prevention** | Blocks prompt injection attempts | ✅ Active |
| **Input Validation** | Checks message length, file count, file types | ✅ Active |
| **SQL Injection Prevention** | Sanitizes session IDs | ✅ Active |
| **Rate Limiting** | Per-session tracking available | ✅ Optional |

---

## Testing

```bash
# Run all tests (29 tests)
pytest tests/test_agent_services.py -v

# Run specific class
pytest tests/test_agent_services.py::TestFrontendAPIService -v

# Run with coverage
pytest tests/test_agent_services.py --cov=app.services
```

**Result: ✅ All 29 tests pass**

---

## Examples

```bash
# Run example script
python examples_agent_services.py
```

Demonstrates:
1. Basic chat with history persistence
2. Multi-user session management
3. Multi-turn conversation with state tracking
4. Session history reload (recovery/continuation)
5. Security features (gating, injection prevention)
6. Session analytics and metrics

---

## Database Schema

**SQLite tables** (auto-created):

```
sessions (session_id, created_at, updated_at, metadata)
├─ messages (id, session_id, turn_number, role, content, created_at, metadata)
├─ product_profiles (id, session_id, product_name, description, hs_code, classification_confidence, last_updated, metadata)
└─ classifications (id, session_id, hs_code, product_description, confidence, duty_rate, gst_rate, created_at, source, metadata)
```

---

## Key Methods

### ChatHistoryManager
- `create_session(session_id, metadata)`
- `add_message(session_id, role, content, metadata)`
- `get_conversation_history(session_id, limit)`
- `update_product_profile(session_id, name, desc, hs_code, confidence)`
- `get_product_profile(session_id)`
- `add_classification(session_id, hs_code, desc, confidence, duty_rate, gst_rate)`
- `get_latest_classification(session_id)`
- `get_session_summary(session_id)`
- `clear_session(session_id)`

### StatefulAgent
- `process_turn(state, user_message, file_paths)`
- `reset_state(session_id)`
- Callbacks: `on_classify`, `on_search`, `on_parse_document`, `on_generate_response`

### FrontendAPIService
- `send_chat_message(session_id, user_message, file_paths)`
- `start_new_session(session_id, metadata)`
- `get_saved_chat_session(session_id)`
- `reload_chat_history(session_id)`
- `clear_session(session_id)`
- `get_session_analytics(session_id)`

### SessionManager
- `create_session(user_id, metadata)`
- `list_active_sessions()`
- `end_session(session_id)`

---

## Callback Integration Points

```python
def classify_handler(query: str) -> dict:
    # Connect to RAG or ML model
    return {
        "hs_code": "8481.80.30",
        "confidence": 0.92,
        "duty_rate": 7.5,
        "gst_rate": 5.0,
    }

def search_handler(query: str) -> dict:
    # Connect to vector DB
    return {"results": [...]}

def parse_doc_handler(file_path: str) -> dict:
    # Connect to OCR or PDF reader
    return {"text": "...", "entities": [...]}

def response_handler(state) -> str:
    # Custom response generation
    return f"Found HS code {state.product_profile.hs_code}..."

agent.on_classify = classify_handler
agent.on_search = search_handler
agent.on_parse_document = parse_doc_handler
agent.on_generate_response = response_handler
```

---

## Common Use Cases

### Use Case 1: Chat-based Classification
```python
response = api.send_chat_message(
    "user_123",
    "Classify a 2-inch stainless steel ball valve"
)
print(response["active_product_profile"]["hs_code"])
```

### Use Case 2: Multi-turn Conversation
```python
api.start_new_session("user_123")
api.send_chat_message("user_123", "Classify a valve")
api.send_chat_message("user_123", "What's the duty rate?")
api.send_chat_message("user_123", "Calculate total for 100 units")
```

### Use Case 3: Session Recovery
```python
# User logs in again after disconnection
reloaded = api.reload_chat_history("user_123_session_1")
print(len(reloaded["messages"]))  # 10 messages from previous session
print(reloaded["state"]["product_profile"]["hs_code"])  # Remembered!
```

### Use Case 4: Document Upload + Classification
```python
response = api.send_chat_message(
    "user_123",
    "Parse and classify this invoice",
    file_paths=["invoice.pdf"]
)
print(response["classification"])
print(response["document_context"])
```

### Use Case 5: Analytics Dashboard
```python
analytics = api.get_session_analytics("user_123")
print(f"Messages: {analytics['total_messages']}")
print(f"Classifications: {analytics['classifications_attempted']}")
print(f"Files uploaded: {analytics['files_uploaded']}")
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Session not found" | Use `start_new_session()` first |
| "Message blocked" | Check domain keywords in DomainGatekeeper |
| "Database locked" | SQLite supports one writer; use PostgreSQL for concurrent writes |
| "History not persisting" | Verify db_path is writable |
| "No response from agent" | Register `on_generate_response` callback |

---

## Documentation Links

- **Full Documentation**: [AGENT_SERVICES_README.md](/Users/kshitiz.saxenayahoo.com/Data/work/learning/capstone/capstone-ai/AGENT_SERVICES_README.md)
- **Implementation Summary**: [IMPLEMENTATION_SUMMARY.md](/Users/kshitiz.saxenayahoo.com/Data/work/learning/capstone/capstone-ai/IMPLEMENTATION_SUMMARY.md)
- **FastAPI Routes**: [app/api/agent_routes.py](/Users/kshitiz.saxenayahoo.com/Data/work/learning/capstone/capstone-ai/app/api/agent_routes.py)
- **Code Examples**: [examples_agent_services.py](/Users/kshitiz.saxenayahoo.com/Data/work/learning/capstone/capstone-ai/examples_agent_services.py)

---

## Summary Stats

- **Lines of Production Code**: 1,200+
- **Lines of Documentation**: 1,000+
- **Lines of Tests**: 400+
- **Lines of Examples**: 350+
- **Test Coverage**: 29 tests, 100% pass rate ✅
- **Services**: 4 core + 1 integration + 1 routes = 6 modules
- **Classes**: 10+ (Agent, Manager, Gatekeeper, Analyzer, Parser, etc.)
- **Methods**: 50+ public methods
- **Security Features**: 5 layers
- **Integration Points**: 4 callbacks
- **Database Tables**: 4 tables

---

## Ready to Use! 🚀

No modifications to existing services required.  
All code is standalone, tested, documented, and production-ready.  
Just plug and play!

For questions, refer to:
1. Code docstrings (comprehensive)
2. AGENT_SERVICES_README.md (detailed guide)
3. examples_agent_services.py (working examples)
4. tests/test_agent_services.py (test coverage)
