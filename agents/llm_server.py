import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

class LLMServer:

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        load_dotenv()

        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )

        return response.choices[0].message.content

# 全局单例
_llm_instance: Optional[LLMServer] = None

def get_llm_server() -> LLMServer:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMServer()
    return _llm_instance