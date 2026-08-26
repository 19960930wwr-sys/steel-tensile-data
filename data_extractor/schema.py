from __future__ import annotations

import json
from pathlib import Path

STEEL_TENSILE_TARGETS = [
    "tensile strength",
    "yield strength",
    "total elongation",
    "uniform elongation",
    "strain rate",
    "gauge length",
]

DEFAULT_ACTIONS = [
    "Anneal",
    "Austenitize",
    "Cold Roll",
    "Forging",
    "Heat",
    "Hot Roll",
    "Normalize",
    "Quench",
    "Temper",
    "Water Quench",
]


def compact_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_output_pattern(material_type: str = "steel", targets=None) -> list[dict]:
    targets = list(targets or STEEL_TENSILE_TARGETS)
    record = {
        "doi/standard_number/publication number": "",
        f"{material_type} composition": {},
        "composition unit": "wt% or at%",
        f"{material_type} name": "",
        "sample name": "",
        "distinguishing factor": "",
        "test route/condition": "",
        "synthesis and processing routes": [
            {"action_1(xxx)": "", "condition": ""},
            {"action_2(xxx)": "", "condition": ""},
            {"action_3(xxx)": "", "condition": ""},
        ],
    }
    for target in targets:
        record[target] = {
            "name": "",
            "value": "",
            "unit": "",
            "test condition": "",
            "sourced figure": ["Figure 1", "Figure x"],
        }
    return [record]


def build_noinfo_pattern(material_type: str = "steel", targets=None) -> list[dict]:
    targets = list(targets or STEEL_TENSILE_TARGETS)
    record = build_output_pattern(material_type, targets)[0]
    record["composition unit"] = ""
    record[f"{material_type} composition"] = ""
    record["synthesis and processing routes"] = ""
    for target in targets:
        record[target] = {
            "value": "",
            "unit": "",
            "test condition": "",
            "sourced figure": [""],
        }
    return [record]


def load_schema_template(path: str | Path | None = None, material_type: str = "steel", targets=None):
    if path is None:
        return build_output_pattern(material_type, targets)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

