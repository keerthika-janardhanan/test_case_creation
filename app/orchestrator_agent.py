import os
import json
from typing import Dict, List
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, SequentialChain
from langchain_openai import AzureChatOpenAI

CACHE_FILE = "./draft_cache.json"

def load_draft_cache() -> Dict:
    """Load cached drafts from disk."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_draft_cache(cache: Dict):
    """Save cache to disk."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

class OrchestratorAgent:
    def __init__(self):
        """Initialize Azure OpenAI LLM and load draft cache."""
        self.llm = AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )
        self.cache = load_draft_cache()

    def generate_draft_steps(self, user_keywords: str, context: str = "") -> Dict:
        """
        Generate draft test steps using LLM. 
        Returns dict: {"draft_steps": str, "variations": str, "version": int}
        """
        key = user_keywords.strip()

        # Check cache
        if key in self.cache:
            last_version = self.cache[key]["version"] + 1
        else:
            last_version = 1

        # Draft Steps Chain
        draft_prompt = PromptTemplate(
            input_variables=["user_input", "context"],
            template="""
            You are an AI agent generating Playwright test steps.
            User input: {user_input}
            Context from artifacts: {context}
            Provide multiple step combinations in numbered format. Await user confirmation.
            """
        )
        draft_chain = LLMChain(llm=self.llm, prompt=draft_prompt, output_key="draft_steps")

        # Variations Chain
        variation_prompt = PromptTemplate(
            input_variables=["draft_steps"],
            template="""
            Given these steps:
            {draft_steps}
            Suggest 2-3 alternative variations for testing.
            """
        )
        variation_chain = LLMChain(llm=self.llm, prompt=variation_prompt, output_key="variations")

        # Sequential Chain
        seq_chain = SequentialChain(
            chains=[draft_chain, variation_chain],
            input_variables=["user_input", "context"],
            output_variables=["draft_steps", "variations"]
        )

        try:
            outputs = seq_chain.invoke({"user_input": user_keywords, "context": context})
        except Exception as e:
            outputs = {
                "draft_steps": f"# Draft steps not generated due to LLM error: {str(e)}",
                "variations": "# Variations unavailable"
            }

        # Add version info and history
        outputs["version"] = last_version
        outputs["history"] = [outputs.copy()]  # keep first draft in history

        # Save to cache
        self.cache[key] = outputs
        save_draft_cache(self.cache)

        return outputs

    def apply_feedback(self, user_keywords: str, feedback: str) -> Dict:
        """
        Apply incremental feedback to last draft steps.
        Returns updated draft dict.
        """
        key = user_keywords.strip()
        if key not in self.cache:
            raise ValueError("No draft exists for given keywords. Generate draft first.")

        last_draft = self.cache[key]
        updated_draft = last_draft.copy()

        if feedback.strip():
            updated_draft["draft_steps"] = feedback.strip()
            updated_draft["version"] += 1
            # Keep history
            if "history" not in updated_draft:
                updated_draft["history"] = []
            updated_draft["history"].append({"draft_steps": feedback.strip(), "version": updated_draft["version"]})

        # Save updated draft to cache
        self.cache[key] = updated_draft
        save_draft_cache(self.cache)

        return updated_draft

    def preview_script(self, test_name: str, steps: str):
        from codegen_utils import generate_final_script
        # If steps is a string (no structure), just pass steps
        if isinstance(steps, str):
            return generate_final_script(test_name, steps)
        # If steps is a dict with structure, pass the step string only
        else:
            step_text = steps.get("draft_steps", "")  # or "steps" key depending on your dict
            return generate_final_script(test_name, step_text)

    def get_draft_history(self, user_keywords: str) -> List[Dict]:
        """Return the list of all versions of draft for a given keyword."""
        key = user_keywords.strip()
        if key in self.cache:
            return self.cache[key].get("history", [])
        return []
