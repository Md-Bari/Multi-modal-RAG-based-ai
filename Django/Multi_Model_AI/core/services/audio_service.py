import logging
import requests
import os
from openai import OpenAI

logger = logging.getLogger(__name__)

class AudioService:
    @staticmethod
    def speech_to_text(audio_file_path: str) -> str:
        """
        Transcribe audio file path using OpenAI's Whisper API.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key == "mock-openai-key-replace-me":
            logger.warning("No valid OPENAI_API_KEY found for Whisper transcription. Returning mockup text.")
            return "This is a mock transcript of the user recording (API key not configured)."

        try:
            client = OpenAI(api_key=api_key)
            with open(audio_file_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
            return transcription.text
        except Exception as e:
            logger.error(f"Whisper transcription failed: {str(e)}")
            return f"[Transcription error: {str(e)}]"

    @staticmethod
    def text_to_speech(text: str) -> bytes:
        """
        Synthesize speech from text using Kokoro.
        If KOKORO_API_URL is configured, POST to it. Otherwise, return mock audio bytes.
        """
        api_url = os.environ.get("KOKORO_API_URL")
        if not api_url:
            logger.warning("KOKORO_API_URL is not set. Generating mock audio bytes.")
            # Return dummy WAV file header + silence
            return b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"

        try:
            response = requests.post(api_url, json={"text": text}, timeout=10)
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Kokoro service returned status code {response.status_code}")
        except Exception as e:
            logger.error(f"Kokoro service call failed: {str(e)}")
        
        # Fallback to mock silent audio bytes
        return b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
