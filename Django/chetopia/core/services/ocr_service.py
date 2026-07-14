import logging
from PIL import Image
import io

logger = logging.getLogger(__name__)

try:
    import pytesseract
except ImportError:
    pytesseract = None

class OCRService:
    @staticmethod
    def extract_text(file_content: bytes) -> str:
        """
        Extract text from image bytes using pytesseract.
        """
        if pytesseract is None:
            logger.warning("pytesseract is not installed. Returning empty OCR text.")
            return "[OCR not available: pytesseract not installed]"

        try:
            image = Image.open(io.BytesIO(file_content))
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            logger.error(f"Failed to perform OCR on image: {str(e)}")
            # Return a warning stub rather than crashing
            return f"[OCR execution failed: {str(e)}]"
