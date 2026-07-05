from app.agents.base import BaseAgent
from app.utils.logger import logger

class FormattingAgent(BaseAgent):
    """
    Agent responsible for normalizing markdown syntax, fixing nested list indentations,
    standardizing tables, and repairing double-spacing issues.
    """
    
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        self.system_prompt = self.load_prompt_file("formatting_prompt.txt")
        
    def format_markdown(self, raw_markdown: str, additional_context: str = "") -> str:
        """
        Invokes LLM to format and repair the styling of a markdown block.
        If validation errors are passed in via additional_context, appends them to prompt.
        """
        logger.info("FormattingAgent: Running markdown normalization...")
        user_content = raw_markdown
        if additional_context:
            user_content = (
                f"### ORIGINAL CONTENT:\n{raw_markdown}\n\n"
                f"### PREVIOUS VALIDATION ERRORS (MUST REPAIR THESE SPECIFICALLY):\n{additional_context}\n"
            )
            
        return self.generate_completion(
            system_prompt=self.system_prompt,
            user_content=user_content,
            temperature=0.15
        )
