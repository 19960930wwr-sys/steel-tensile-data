from __future__ import annotations

from .context import ArticleContext
from .schema import compact_json


STAGE1_SYSTEM_PROMPT = (
    "You are a careful scientific information extraction assistant. "
    "Your priority is exhaustive table-value enumeration, not summarization."
)

STAGE2_SYSTEM_PROMPT = (
    "You are a material science scientist and a strict data integration assistant. "
    "Use mandatory property evidence as anchors and do not invent property values."
)

REPAIR_SYSTEM_PROMPT = (
    "You are a data-format fixer. Repair malformed JSON/Python list/dict output. "
    "Only fix brackets, braces, commas, quotes, booleans, and null values. "
    "Do not change field names, values, units, capitalization, or labels. "
    "Return only a valid top-level list of dictionaries."
)


def build_stage1_prompt(targets: list[str], context: ArticleContext) -> str:
    return f"""
Target properties:
{compact_json(targets)}

Task:
Extract every explicitly reported value for the target properties from text, tables, and figure/table captions.
This step is only for property evidence. Do not merge values into material records.

Table-first extraction rules:
1. TABLES are the primary evidence source. Scan every table before using ARTICLE_TEXT.
2. A table is relevant if a target property appears in its caption, footnote, any header, any row label, any column label, or nearby table-related text.
3. For each relevant table, identify the full table region governed by the target-property label.
4. If a relevant table is a matrix, output one evidence item for every explicit data cell in the target-property region.
5. Preserve sample, group, category, condition, treatment, and measurement-variant labels in local_labels.
6. Do not infer values. Preserve raw expressions, including ranges, inequalities and +/- notation.
7. Return ONLY a JSON array.

Evidence item schema:
[
  {{
    "property": "one target property name",
    "value": "raw reported value exactly as written",
    "unit": "unit if explicit or implied by table header",
    "source_id": "copy the exact source_id from the source block",
    "source_type": "pdf/xml/html/json/table/text/figure",
    "page_idx": "PDF page_idx if available, otherwise empty string",
    "section": "section title if available",
    "source": "table/figure/text label if available",
    "local_labels": ["row/column/sample/group labels needed to identify the value"],
    "test_condition": "test condition associated with the value, if available",
    "evidence_text": "short source snippet or table-cell context"
  }}
]

ARTICLE_TEXT_WITH_SOURCE_BLOCKS:
{context.prompt_text()}

TABLES:
{context.table_text}
"""


def build_stage2_prompt(
    material_type: str,
    targets: list[str],
    actions: list[str],
    evidence: list[dict],
    output_pattern: list[dict],
    context: ArticleContext,
) -> str:
    return f"""
Target material type:
{material_type}

Target properties:
{compact_json(targets)}

Allowed/expected synthesis and processing actions:
{compact_json(actions)}

Final output pattern:
{compact_json(output_pattern)}

PROPERTY_EVIDENCE:
{compact_json(evidence)}

Task:
Create final material records by filling doi/standard_number/publication number, material/sample identity, composition, distinguishing factors, synthesis and processing routes, test conditions, and property fields.

Mandatory rules:
1. Every item in PROPERTY_EVIDENCE must appear in the final output exactly once unless it is an exact duplicate.
2. Do not add any target-property value that is not present in PROPERTY_EVIDENCE.
3. If the current final schema cannot store multiple values for the same material/sample/property in one record, create separate records.
4. Use ARTICLE_TEXT and TABLES only to fill non-property context such as doi, material name, sample name, composition, distinguishing factor, route, and test condition.
5. If context is not explicit, leave the field empty. Do not infer.
6. Return ONLY the complete Python/JSON-style list of dictionaries.

ARTICLE_TEXT:
{context.full_text}

TABLES:
{context.table_text}
"""


def build_repair_prompt(raw_output: str) -> str:
    return f"Malformed extraction output:\n{raw_output}"

