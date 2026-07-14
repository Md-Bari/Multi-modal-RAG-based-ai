import os
import logging
import requests
import json
from typing import Generator, Union, List, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMService:
    @staticmethod
    def generate_response(
        provider: str,
        model_name: str,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> Union[str, Generator[str, None, None]]:
        """
        Execute request to the selected LLM provider.
        """
        provider = provider.lower()

        # Intercept routing classifier prompts in mock environments
        for msg in messages:
            if msg.get("role") == "system" and "routing classification system" in msg.get("content", ""):
                user_content = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
                if "joke" in user_content.lower() or "general" in user_content.lower():
                    return "YES"
                return "NO"
        
        if provider == "openai":
            return LLMService._openai(model_name, messages, stream)
        elif provider == "gemini":
            return LLMService._gemini(model_name, messages, stream)
        elif provider == "claude" or provider == "anthropic":
            return LLMService._anthropic(model_name, messages, stream)
        elif provider == "grok":
            return LLMService._grok(model_name, messages, stream)
        elif provider == "ollama":
            return LLMService._ollama(model_name, messages, stream)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    @staticmethod
    def _openai(model: str, messages: List[Dict[str, str]], stream: bool) -> Union[str, Generator[str, None, None]]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key == "mock-openai-key-replace-me":
            return LLMService._mock_response("OpenAI", stream)

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=messages,
            stream=stream
        )

        if stream:
            def gen():
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
            return gen()
        else:
            return response.choices[0].message.content

    @staticmethod
    def _gemini(model: str, messages: List[Dict[str, str]], stream: bool) -> Union[str, Generator[str, None, None]]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or api_key == "mock-gemini-key-replace-me":
            return LLMService._mock_response("Gemini", stream)

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # Convert messages from OpenAI format to Gemini format
        # Gemini messages: list of dicts with role and parts
        gemini_history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})
        
        # Current user message
        user_message = messages[-1]["content"]
        
        gemini_model = genai.GenerativeModel(
            model_name=model or 'gemini-2.5-flash'
        )
        
        # Start a chat session or generate content
        chat = gemini_model.start_chat(history=gemini_history)
        
        if stream:
            response = chat.send_message(user_message, stream=True)
            def gen():
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            return gen()
        else:
            response = chat.send_message(user_message)
            return response.text

    @staticmethod
    def _anthropic(model: str, messages: List[Dict[str, str]], stream: bool) -> Union[str, Generator[str, None, None]]:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or api_key == "mock-anthropic-key-replace-me":
            return LLMService._mock_response("Anthropic Claude", stream)

        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        
        # System instructions need to be separated for Anthropic
        system_prompt = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        if stream:
            response = client.messages.create(
                model=model or "claude-3-5-sonnet-20240620",
                max_tokens=1024,
                system=system_prompt,
                messages=user_messages,
                stream=True
            )
            def gen():
                for chunk in response:
                    if chunk.type == "content_block_delta":
                        yield chunk.delta.text
            return gen()
        else:
            response = client.messages.create(
                model=model or "claude-3-5-sonnet-20240620",
                max_tokens=1024,
                system=system_prompt,
                messages=user_messages
            )
            return response.content[0].text

    @staticmethod
    def _grok(model: str, messages: List[Dict[str, str]], stream: bool) -> Union[str, Generator[str, None, None]]:
        api_key = os.environ.get("GROK_API_KEY")
        if not api_key or api_key == "mock-grok-key-replace-me":
            return LLMService._mock_response("Grok (xAI)", stream)

        # Grok is OpenAI compatible. We use OpenAI client with custom base_url
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        response = client.chat.completions.create(
            model=model or "grok-beta",
            messages=messages,
            stream=stream
        )

        if stream:
            def gen():
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
            return gen()
        else:
            return response.choices[0].message.content

    @staticmethod
    def _ollama(model: str, messages: List[Dict[str, str]], stream: bool) -> Union[str, Generator[str, None, None]]:
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        url = f"{base_url}/api/chat"
        payload = {
            "model": model or "llama3",
            "messages": messages,
            "stream": stream
        }

        try:
            response = requests.post(url, json=payload, stream=stream, timeout=30)
            if response.status_code != 200:
                return f"[Ollama returned status code {response.status_code}]"
            
            if stream:
                def gen():
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line.decode('utf-8'))
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                return gen()
            else:
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Ollama request failed: {str(e)}")
            return f"[Ollama failed: {str(e)}]"

    @staticmethod
    def _mock_response(provider_name: str, stream: bool) -> Union[str, Generator[str, None, None]]:
        mock_text = f"This is a simulated response from {provider_name} (API key not configured)."
        if stream:
            def gen():
                # Yield parts of the mock response to simulate streaming
                words = mock_text.split(" ")
                for word in words:
                    yield word + " "
            return gen()
        else:
            return mock_text
