"""Service helpers for test case generation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..test_case_generator import TestCaseGenerator, map_llm_to_template
from ..vector_db import VectorDBClient


class TestCaseGenerationError(RuntimeError):
    """Raised when the generator fails to produce test cases."""


class TestCaseService:
    """Facade around TestCaseGenerator with optional template support."""

    def __init__(self, db_client: Optional[VectorDBClient] = None) -> None:
        self._db = db_client or VectorDBClient()
        self._generator: Optional[TestCaseGenerator] = None

    def _get_generator(self) -> TestCaseGenerator:
        if self._generator is None:
            self._generator = TestCaseGenerator(self._db)
        return self._generator

    def generate(
        self,
        story: str,
        llm_only: bool = False,
        template_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if not story or not story.strip():
            raise TestCaseGenerationError("Story text is required.")

        generator = self._get_generator()
        results = generator.generate_test_cases(story.strip(), llm_only=llm_only)
        if template_df is not None:
            df = map_llm_to_template(results, template_df)
        else:
            df = pd.DataFrame(results)

        return {
            "records": results,
            "dataframe": df,
        }


def load_template_bytes(template_path: Path) -> pd.DataFrame:
    """Load an Excel template into a DataFrame for mapping results."""

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    if template_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError("Only Excel templates are supported in this slice.")
    return pd.read_excel(template_path)


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to XLSX bytes."""

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="TestCases")
    buffer.seek(0)
    return buffer.read()
