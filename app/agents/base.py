from pathlib import Path
from openai import OpenAI
from app.config.settings import settings
from app.utils.logger import logger

class BaseAgent:
    """
    Base class for semantic publishing pipeline agents.
    Provides standard access to the modular LLM client and prompt utilities.
    """
    
    def __init__(self, api_key: str = None):
        # Configure the modular client
        import os
        if not api_key:
            api_key = settings.LLM_API_KEY
            if not api_key or "placeholder" in api_key.lower() or api_key == "your-api-key-here":
                api_key = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
            
        if not api_key:
            api_key = "placeholder-key"
            
        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.LLM_BASE_URL
        )
        self.model = settings.LLM_MODEL
        logger.info(f"Initialized agent with Model: {self.model} and URL: {settings.LLM_BASE_URL}")

    def load_prompt_file(self, filename: str) -> str:
        """Loads prompt template from the prompts/ folder."""
        prompt_path = settings.PROMPTS_DIR / filename
        if not prompt_path.exists():
            # If prompt file does not exist, return a fallback template
            raise FileNotFoundError(f"System prompt file not found at: {prompt_path}")
            
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def generate_completion(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> str:
        """Helper to invoke LLM completion synchronously with exponential backoff for rate limits."""
        import time
        max_retries = 7
        backoff_factor = 2
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=temperature
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                is_rate_limit = False
                err_msg = str(e).lower()
                transient_keywords = [
                    "rate limit", "429", "quota", "resource_exhausted", 
                    "503", "500", "502", "504", "unavailable", "overloaded", 
                    "high demand", "try again", "timeout", "connection"
                ]
                if any(kw in err_msg for kw in transient_keywords):
                    is_rate_limit = True
                    
                if is_rate_limit and attempt < max_retries - 1:
                    sleep_time = (backoff_factor ** attempt) * 5
                    logger.warning(f"BaseAgent: Rate limit hit. Retrying in {sleep_time}s (Attempt {attempt+1}/{max_retries})...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Error invoking LLM backend after {attempt+1} attempts: {e}")
                    raise e
