from __future__ import annotations
from typing import List, Dict, Any

import os
from typing import Any

import requests

class AnswerGenerator:
    """Generate a relevant answer from retrieved documents."""

    def __init__(self, gemini_api_key: str | None = None) -> None:
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")

    def generate(self, query: str, context: str) -> str:
        if self.gemini_api_key:
            return self._generate_with_gemini(query, context)
        return self._generate_locally(query, context)

    def _generate_locally(self, query: str, context: str) -> str:
        if not context:
            return "I could not find relevant information for that question in the vector database."

        relevant_snippets = []
        relevant_snippets = context.split("\n\n")[:5]
        context = "\n\n".join(relevant_snippets)
        if not context:
            return "I found matching records, but their content is empty or unavailable."

        answer = (
            "Based on the retrieved context, here is a likely answer:\n\n"
            f"{context[:3000]}"
            "\n\nIf you need a more precise answer, refine your query or provide more context."
        )
        return answer

    def _generate_with_gemini(self, query: str, context: str) -> str:
        
        system_instruction = (
            "You are a precise document assistant. "
            "Answer the user's question using ONLY the provided context. "
            "If the answer is not in the context, say: "
            "'I don't know based on the provided document.' "
            "Be concise and cite the Section and Chapter number where relevant."
        )
        
        user_msg = f"""Context:
            {context}

            Question: {query}"""

        if not context:
            return self._generate_locally(query, context)

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_msg}]}],
            "generationConfig": {"temperature": 0.2},
        }

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent",
            params={"key": self.gemini_api_key},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        payload_data = response.json()
        return payload_data["candidates"][0]["content"]["parts"][0]["text"].strip()
