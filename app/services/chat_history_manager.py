"""
Chat History Manager Service

Manages persistent conversation state with SQLite backend.
Stores and retrieves message history, product profiles, and classification context
across multi-turn interactions.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ChatHistoryManager:
    """Manages persistent chat history and session state."""

    def __init__(self, db_path: str = "chat_history.db"):
        """
        Initialize chat history manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id, turn_number)
                )
            """)
            
            # Product profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    product_name TEXT,
                    description TEXT,
                    hs_code TEXT,
                    classification_confidence REAL,
                    last_updated TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id)
                )
            """)
            
            # Classifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    hs_code TEXT NOT NULL,
                    product_description TEXT,
                    confidence REAL,
                    duty_rate REAL,
                    gst_rate REAL,
                    created_at TEXT NOT NULL,
                    source TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            
            conn.commit()

    def create_session(self, session_id: str, metadata: Optional[dict] = None) -> None:
        """
        Create a new chat session.
        
        Args:
            session_id: Unique session identifier
            metadata: Optional session metadata
        """
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sessions (session_id, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?)
            """, (session_id, now, now, json.dumps(metadata or {})))
            conn.commit()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Add a message to session history.
        
        Args:
            session_id: Session identifier
            role: Message role ("user" or "assistant")
            content: Message content
            metadata: Optional message metadata
        """
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get next turn number
            cursor.execute(
                "SELECT MAX(turn_number) FROM messages WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()
            turn_number = (result[0] or 0) + 1
            
            cursor.execute("""
                INSERT INTO messages (session_id, turn_number, role, content, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, turn_number, role, content, now, json.dumps(metadata or {})))
            
            # Update session timestamp
            cursor.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id)
            )
            conn.commit()

    def get_conversation_history(self, session_id: str, limit: Optional[int] = None) -> list[dict]:
        """
        Retrieve conversation history for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return (None = all)
        
        Returns:
            List of message dictionaries with role and content
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT role, content, created_at, metadata
                FROM messages
                WHERE session_id = ?
                ORDER BY turn_number ASC
            """
            params = [session_id]
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata"] or "{}")
                }
                for row in rows
            ]

    def update_product_profile(
        self,
        session_id: str,
        product_name: str,
        description: str,
        hs_code: str,
        confidence: float = 0.0,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Update the product profile for a session.
        
        Args:
            session_id: Session identifier
            product_name: Product name
            description: Product description
            hs_code: ITC-HS code
            confidence: Classification confidence (0-1)
            metadata: Optional additional metadata
        """
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO product_profiles
                (session_id, product_name, description, hs_code, classification_confidence, last_updated, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                product_name,
                description,
                hs_code,
                confidence,
                now,
                json.dumps(metadata or {})
            ))
            conn.commit()

    def get_product_profile(self, session_id: str) -> Optional[dict]:
        """
        Retrieve the current product profile for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Product profile dictionary or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM product_profiles WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                "product_name": row["product_name"],
                "description": row["description"],
                "hs_code": row["hs_code"],
                "classification_confidence": row["classification_confidence"],
                "last_updated": row["last_updated"],
                "metadata": json.loads(row["metadata"] or "{}")
            }

    def add_classification(
        self,
        session_id: str,
        hs_code: str,
        product_description: str,
        confidence: float,
        duty_rate: Optional[float] = None,
        gst_rate: Optional[float] = None,
        source: str = "ml_model",
        metadata: Optional[dict] = None
    ) -> None:
        """
        Record a classification result.
        
        Args:
            session_id: Session identifier
            hs_code: ITC-HS code
            product_description: Product description
            confidence: Classification confidence (0-1)
            duty_rate: Basic Customs Duty rate
            gst_rate: GST rate
            source: Source of classification
            metadata: Optional metadata
        """
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO classifications
                (session_id, hs_code, product_description, confidence, duty_rate, gst_rate, created_at, source, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                hs_code,
                product_description,
                confidence,
                duty_rate,
                gst_rate,
                now,
                source,
                json.dumps(metadata or {})
            ))
            conn.commit()

    def get_latest_classification(self, session_id: str) -> Optional[dict]:
        """
        Get the most recent classification for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Classification dictionary or None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM classifications
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                "hs_code": row["hs_code"],
                "product_description": row["product_description"],
                "confidence": row["confidence"],
                "duty_rate": row["duty_rate"],
                "gst_rate": row["gst_rate"],
                "created_at": row["created_at"],
                "source": row["source"],
                "metadata": json.loads(row["metadata"] or "{}")
            }

    def get_session_summary(self, session_id: str) -> dict:
        """
        Get a comprehensive summary of a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session summary with messages, profile, and classifications
        """
        return {
            "session_id": session_id,
            "messages": self.get_conversation_history(session_id),
            "product_profile": self.get_product_profile(session_id),
            "latest_classification": self.get_latest_classification(session_id)
        }

    def clear_session(self, session_id: str) -> None:
        """
        Clear all data for a session.
        
        Args:
            session_id: Session identifier
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM product_profiles WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM classifications WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
