import os
import logging
import requests
import json
from core.services.llm_service import LLMService
from core.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

class VisionService:
    @staticmethod
    def caption_image(image_bytes: bytes) -> str:
        """
        Caption an image using Ollama's vision model.
        Falls back to OCR-only if vision model is unavailable.
        """
        vision_model = LLMService.get_vision_model()
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        # First, run OCR to get any text
        ocr_text = OCRService.extract_text(image_bytes)
        extracted_text = ocr_text if ocr_text and "[OCR" not in ocr_text else ""

        try:
            import base64
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")

            payload = {
                "model": vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image in detail. Include any text you see."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ],
                "stream": False
            }

            response = requests.post(f"{base_url}/api/chat", json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                caption = data.get("message", {}).get("content", "")
                if caption:
                    result = caption
                    if extracted_text:
                        result += f"\n\n[OCR Extracted Text]:\n{extracted_text}"
                    return result
        except Exception as e:
            logger.error(f"Vision model captioning failed: {str(e)}")

        # Fallback to OCR-only
        if extracted_text:
            return f"[Image - OCR extracted text]:\n{extracted_text}"
        return "[Image uploaded - no caption available]"
