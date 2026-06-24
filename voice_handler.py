import os
import asyncio
from groq import Groq


class VoiceHandler:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=api_key) if api_key else None

    async def transcribe(self, file_path: str) -> str | None:
        if not self.client:
            return None
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._transcribe_sync, file_path)
            return result
        except Exception as e:
            print(f"Voice transcription error: {e}")
            return None

    def _transcribe_sync(self, file_path: str) -> str | None:
        try:
            with open(file_path, "rb") as f:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), f.read()),
                    model="whisper-large-v3",
                    language="ru",
                    response_format="text"
                )
            return transcription.strip() if transcription else None
        except Exception as e:
            print(f"Groq transcription error: {e}")
            return None
