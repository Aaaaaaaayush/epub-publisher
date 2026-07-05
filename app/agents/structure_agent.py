from app.agents.base import BaseAgent
from app.utils.logger import logger

class StructureAgent(BaseAgent):
    """
    Agent responsible for correcting document section heading hierarchies
    without modifying educational meaning or text contents.
    """
    
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        self.system_prompt = self.load_prompt_file("structure_prompt.txt")
        
    def repair_structure(self, raw_markdown: str) -> str:
        """
        Invokes LLM to check and normalize the structural hierarchy of a markdown block.
        """
        logger.info("StructureAgent: Repairing heading hierarchy...")
        return self.generate_completion(
            system_prompt=self.system_prompt,
            user_content=raw_markdown,
            temperature=0.1
        )
