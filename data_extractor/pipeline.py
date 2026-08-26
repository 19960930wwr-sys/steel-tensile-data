from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .context import ArticleContext, load_article_context
from .llm import llm_client
from .postprocess import (
    deduplicate_records,
    ensure_records_list,
    filter_extracted_results,
    normalize_evidence,
    parse_model_output,
    repair_output_with_llm,
)
from .prompts import build_stage1_prompt, build_stage2_prompt, STAGE1_SYSTEM_PROMPT, STAGE2_SYSTEM_PROMPT
from .schema import DEFAULT_ACTIONS, STEEL_TENSILE_TARGETS, build_noinfo_pattern, build_output_pattern


def extract_two_stage(
    context: ArticleContext,
    api_key: str,
    model_name: str,
    material_type: str = "steel",
    targets: list[str] | None = None,
    actions: list[str] | None = None,
    base_url: str | None = None,
    token_limit: int = 64000,
):
    targets = list(targets or STEEL_TENSILE_TARGETS)
    actions = list(actions or DEFAULT_ACTIONS)
    output_pattern = build_output_pattern(material_type, targets)

    stage1_prompt = build_stage1_prompt(targets, context)
    if len(stage1_prompt) > token_limit:
        raise ValueError(f"Stage-1 prompt exceeds the soft limit of {token_limit} characters.")

    raw_evidence = llm_client(
        STAGE1_SYSTEM_PROMPT,
        stage1_prompt,
        api_key,
        model_name=model_name,
        base_url=base_url,
    )
    evidence, evidence_raw = parse_model_output(raw_evidence)
    if evidence is None and evidence_raw:
        evidence = repair_output_with_llm(evidence_raw, api_key, model_name, base_url)
    evidence = normalize_evidence(evidence)

    stage2_prompt = build_stage2_prompt(material_type, targets, actions, evidence, output_pattern, context)
    if len(stage2_prompt) > token_limit:
        raise ValueError(f"Stage-2 prompt exceeds the soft limit of {token_limit} characters.")

    raw_records = llm_client(
        STAGE2_SYSTEM_PROMPT,
        stage2_prompt,
        api_key,
        model_name=model_name,
        base_url=base_url,
    )
    records, records_raw = parse_model_output(raw_records)
    if records is None and records_raw:
        records = repair_output_with_llm(records_raw, api_key, model_name, base_url)

    records = ensure_records_list(records)
    records = deduplicate_records(records)
    records = filter_extracted_results(targets, context.full_text + "\n" + context.table_text, records, evidence)

    return {
        "records": records,
        "property_evidence": evidence,
        "output_pattern": output_pattern,
        "noinfo_pattern": build_noinfo_pattern(material_type, targets),
        "stage1_prompt": stage1_prompt,
        "stage2_prompt": stage2_prompt,
    }


def _flatten_record(record, prefix=""):
    flat = {}
    for key, value in record.items():
        name = f"{prefix}{key}" if not prefix else f"{prefix}__{key}"
        if isinstance(value, dict):
            flat.update(_flatten_record(value, name))
        elif isinstance(value, list):
            flat[name] = json.dumps(value, ensure_ascii=False)
        else:
            flat[name] = value
    return flat


def save_outputs(payload: dict, output_dir: str | Path, stem: str):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}_records.json"
    evidence_path = output_dir / f"{stem}_evidence.json"
    csv_path = output_dir / f"{stem}_records.csv"
    xlsx_path = output_dir / f"{stem}_records.xlsx"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload["records"], handle, ensure_ascii=False, indent=2)
    with evidence_path.open("w", encoding="utf-8") as handle:
        json.dump(payload["property_evidence"], handle, ensure_ascii=False, indent=2)

    flat_records = pd.DataFrame([_flatten_record(item) for item in payload["records"]])
    flat_records.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            flat_records.to_excel(writer, sheet_name="records", index=False)
            pd.DataFrame(payload["property_evidence"]).to_excel(writer, sheet_name="evidence", index=False)
    except Exception:
        if xlsx_path.exists():
            xlsx_path.unlink(missing_ok=True)

    return {
        "json": json_path,
        "csv": csv_path,
        "xlsx": xlsx_path if xlsx_path.exists() else None,
        "evidence": evidence_path,
    }


def run_batch(
    input_path: str | Path,
    output_dir: str | Path,
    api_key: str,
    model_name: str,
    material_type: str = "steel",
    targets: list[str] | None = None,
    actions: list[str] | None = None,
    base_url: str | None = None,
):
    input_path = Path(input_path)
    if input_path.is_dir():
        paths = sorted(
            p for p in input_path.iterdir() if p.suffix.lower() in {".json", ".xml", ".html", ".htm", ".txt"}
        )
    else:
        paths = [input_path]

    outputs = []
    for path in paths:
        context = load_article_context(path)
        payload = extract_two_stage(
            context=context,
            api_key=api_key,
            model_name=model_name,
            material_type=material_type,
            targets=targets,
            actions=actions,
            base_url=base_url,
        )
        outputs.append(save_outputs(payload, output_dir, path.stem))
    return outputs

