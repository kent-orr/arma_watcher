from ollama import chat, ChatResponse
from datetime import datetime

from pydantic import BaseModel

MODEL = "gemma4:e4b"

class Inference:
    def __init__(self), prompt = None:
        self.model = MODEL
        self.prompt = if prompt is None  "return an integer for the queue position from the screenshot" else prompt
    
    def run(self, ssmgr:ScreenshotManager):
        response = chat(
            model=self.model,
            messages=[{"role": "user", "content": self.prompt}, {"role": "user", "content": ssmgr.get()}]
        )
        return response

        
