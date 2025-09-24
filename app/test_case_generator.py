import os
import json
import re
import pandas as pd
from vector_db import VectorDBClient
from langchain.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI


class TemplateLoader:
    """Utility to load test case templates from different formats."""

    @staticmethod
    def load_template(file_path: str):
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)

        elif ext in (".yaml", ".yml"):
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        elif ext in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                return {"format": f.read(), "fields": []}

        elif ext in (".csv", ".xlsx"):
            df = pd.read_excel(file_path) if ext == ".xlsx" else pd.read_csv(file_path)
            return {
                "fields": list(df.columns),
                "rows": df.to_dict(orient="records"),
                "format": None,
            }

        else:
            raise ValueError(f"Unsupported template file type: {ext}")


class TestCaseGenerator:
    def __init__(self, db: VectorDBClient, template=None):
        self.db = db
        self.template = template or {}

        # ✅ Use AzureChatOpenAI instead of ChatOpenAI
        self.llm = AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )

        self.prompt = PromptTemplate(
            input_variables=["context", "story"],
            template=(
                "You are a test engineer. Based on the following Jira story and related context, "
                "generate detailed functional test cases in JSON format.\n\n"
                "Jira Story:\n{story}\n\n"
                "Context:\n{context}\n\n"
                "Output strictly as JSON array of test cases with fields: id, title, steps, expected."
            ),
        )

    def generate_test_cases(self, story: str):
        # Retrieve supporting context from vector DB
        context = self.db.query(story, top_k=3)
        ctx = "\n".join([c["content"] for c in context])
        query = self.prompt.format(context=ctx, story=story)

        # LLM call
        resp = self.llm.invoke(query)
        output = resp.content if hasattr(resp, "content") else str(resp)

        # Remove code fences if any
        output = re.sub(r"^```(?:json)?\s*", "", output, flags=re.DOTALL)
        output = re.sub(r"\s*```$", "", output, flags=re.DOTALL).strip()
        output = output.strip()

        # Parse JSON
        try:
            test_cases = json.loads(output)
        except json.JSONDecodeError as e:
            # fallback: return raw string
            print(f"❌ JSON parse error: {e}\nOutput:\n{output}")
            return output

        return test_cases

    def _generate_from_template(self, story: str):
        """Fill test cases using the selected template."""
        lines = [line.strip() for line in story.splitlines() if line.strip()]
        test_cases = []

        if "rows" in self.template:
            # Excel/CSV style template
            for idx, row in enumerate(self.template["rows"], 1):
                test_cases.append({"id": idx, **row})
        else:
            # Format string style (JSON/YAML/TXT)
            for idx, line in enumerate(lines, 1):
                format_str = self.template.get("format", "{title}")
                fields = self.template.get("fields", ["title"])

                filled = format_str
                for field in fields:
                    value = line if field == "title" else f"<{field}_value>"
                    filled = filled.replace(f"{{{field}}}", value)

                test_cases.append({"id": idx, "test_case": filled})

        return test_cases
    
def map_llm_to_template(llm_output, template_df):
    """
    Map LLM output into the structure of the uploaded Excel template.
    - Dynamically detects columns in the template.
    - Fills them with combined LLM test case data.
    """
    row = {}

    for col in template_df.columns:
        col_lower = col.lower()

        if "objective" in col_lower:
            row[col] = " / ".join([tc.get("title", "") for tc in llm_output])

        elif "description" in col_lower:
            lines = []
            for idx, tc in enumerate(llm_output, start=1):
                lines.append(f"Case {idx}")
                for step_num, step in enumerate(tc.get("steps", []), start=1):
                    lines.append(f"{step_num}. {step}")
                if "expected" in tc:
                    lines.append(f"Expected: {tc['expected']}")
                lines.append("")
            row[col] = "\n".join(lines)

        elif "cover" in col_lower:
            row[col] = "<Brand> : <Offering>"

        elif "sc no" in col_lower:
            row[col] = 1

        else:
            row[col] = ""

    return pd.DataFrame([row])


def export_to_excel(mapped_df, output_path="generated_test_cases.xlsx"):
    """Save the mapped DataFrame to an Excel file."""
    mapped_df.to_excel(output_path, index=False)
    return output_path
