from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any

from .llm import llm_client
from .prompts import REPAIR_SYSTEM_PROMPT, build_repair_prompt


def parse_model_output(text):
    if text is None:
        return None, ""

    raw = str(text).strip()
    cleaned = raw
    cleaned = re.sub(r"^```(?:json|python)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = re.sub(r"\bnull\b", "None", cleaned)
    cleaned = re.sub(r"\btrue\b", "True", cleaned)
    cleaned = re.sub(r"\bfalse\b", "False", cleaned)

    candidates = [cleaned]
    match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", cleaned)
    if match:
        candidates.append(match.group(1))

    for candidate in candidates:
        try:
            return json.loads(candidate), raw
        except Exception:
            pass
        try:
            return ast.literal_eval(candidate), raw
        except Exception:
            pass

    return None, raw


def ensure_records_list(parsed):
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def normalize_for_match(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def normalize_reported_value(value):
    value = normalize_for_match(value)
    value = value.replace("±", "+/-").replace("卤", "+/-")
    return re.sub(r"\s+", "", value)


def build_evidence_value_set(evidence):
    values = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value", item.get("reported_value", ""))
        if value:
            values.add(normalize_reported_value(value))
    return values


def value_supported_by_evidence(value, evidence_values):
    normalized_value = normalize_reported_value(value)
    if not normalized_value:
        return False
    if normalized_value in evidence_values:
        return True
    return any(
        normalized_value in evidence_value or evidence_value in normalized_value
        for evidence_value in evidence_values
    )


def repair_output_with_llm(raw_output, api_key, model_name, base_url=None):
    user_prompt = build_repair_prompt(raw_output)
    fixed = llm_client(
        REPAIR_SYSTEM_PROMPT,
        user_prompt,
        api_key,
        model_name=model_name,
        base_url=base_url,
    )
    parsed, _ = parse_model_output(fixed)
    return parsed


def normalize_evidence(evidence):
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence", evidence.get("items", []))
    if not isinstance(evidence, list):
        return []

    normalized = []
    seen = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        prop = str(item.get("property", item.get("property_name", ""))).strip()
        value = str(item.get("value", item.get("reported_value", ""))).strip()
        if not prop or not value:
            continue
        item = dict(item)
        item.setdefault("property", prop)
        item.setdefault("value", value)
        if "reported_unit" in item and "unit" not in item:
            item["unit"] = item["reported_unit"]
        key = (
            prop.lower(),
            value,
            str(item.get("source_id", "")),
            str(item.get("source", "")),
            json.dumps(item.get("local_labels", []), ensure_ascii=False, separators=(",", ":")),
            str(item.get("test_condition", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        item["evidence_id"] = f"E{len(normalized) + 1}"
        normalized.append(item)
    return normalized


def deduplicate_records(records):
    deduped = []
    seen = set()
    for record in records or []:
        if not isinstance(record, dict):
            continue
        marker = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(record)
    return deduped


def filter_extracted_results(properties, original_text, extracted_results, evidence=None):
    filtered_results = []
    original_text_norm = normalize_for_match(original_text)
    evidence_values = build_evidence_value_set(evidence)

    for record in extracted_results or []:
        if not isinstance(record, dict):
            continue
        record = copy.deepcopy(record)
        property_valid = True
        for prop in properties:
            prop_data = record.get(prop)
            if not isinstance(prop_data, dict):
                continue
            prop_value = prop_data.get("value", "")
            if not prop_value:
                continue
            if value_supported_by_evidence(prop_value, evidence_values):
                continue
            if prop_value and normalize_reported_value(prop_value) not in normalize_reported_value(original_text_norm):
                property_valid = False
                break
        if property_valid:
            filtered_results.append(record)

    return filtered_results
