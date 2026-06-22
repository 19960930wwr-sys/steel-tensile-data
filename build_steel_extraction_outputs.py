from __future__ import annotations

import itertools
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_FILE = "ts-ys-te.xlsx"
CATEGORY = "steel_tensile_mechanical"
SOURCE_FOLDER = "steel_data_extraction"

PROPERTY_SPECS = {
    "gauge length": {
        "unit": "mm",
        "group": "length",
        "range": (1e-4, 1000.0),
        "note": "Specimen gauge length; used mainly as testing metadata.",
    },
    "strain rate": {
        "unit": "s^-1",
        "group": "strain_rate",
        "range": (1e-8, 1e4),
        "note": "Test strain rate; loading rates such as MPa/s and mm/min are excluded.",
    },
    "tensile strength": {
        "unit": "MPa",
        "group": "stress",
        "range": (1.0, 5000.0),
        "note": "Ultimate tensile strength in stress units.",
    },
    "yield strength": {
        "unit": "MPa",
        "group": "stress",
        "range": (1.0, 5000.0),
        "note": "Yield strength or proof strength in stress units.",
    },
    "total elongation": {
        "unit": "%",
        "group": "percent",
        "range": (0.0, 200.0),
        "note": "Total elongation; percent units are retained.",
    },
    "uniform elongation": {
        "unit": "%",
        "group": "percent",
        "range": (0.0, 200.0),
        "note": "Uniform elongation; percent units are retained.",
    },
}

PAIR_NOTES = {
    ("yield strength", "tensile strength"): "Strength-strength consistency; usually expected to show positive correlation.",
    ("yield strength", "total elongation"): "Strength-ductility trade-off; useful for mechanical performance map.",
    ("tensile strength", "total elongation"): "Strength-ductility trade-off; useful for mechanical performance map.",
    ("yield strength", "uniform elongation"): "Yield strength versus uniform ductility relation.",
    ("tensile strength", "uniform elongation"): "Tensile strength versus uniform ductility relation.",
    ("total elongation", "uniform elongation"): "Consistency between two ductility descriptors.",
    ("strain rate", "yield strength"): "Rate-sensitive strength relation; interpret with temperature and processing context.",
    ("strain rate", "tensile strength"): "Rate-sensitive strength relation; interpret with temperature and processing context.",
}

EMPTY_STRINGS = {
    "",
    "none",
    "nan",
    "null",
    "n/a",
    "na",
    "not specified",
    "not available",
    "[]",
    "['none']",
    "['None']",
}

LONG_COLUMNS = [
    "category",
    "source_folder",
    "doi_or_file_id",
    "source_file",
    "source_row",
    "record_id",
    "superalloy_name",
    "sample_name",
    "composition_unit_raw",
    "composition_unit_normalized",
    "composition_present_element_count",
    "composition_sum_numeric",
    "distinguishing_factor",
    "synthesis_and_processing_routes",
    "test_route_condition",
    "full_compositions_raw",
    "property_target_raw",
    "property_target_canonical",
    "property_name_raw",
    "property_value_raw",
    "property_unit_raw",
    "property_value_numeric_first",
    "property_numeric_token_count",
    "property_numeric_parse_kind",
    "property_standard_value",
    "property_standard_unit",
    "unit_conversion_note",
    "property_sourced_figure",
    "property_flags",
]

ORIGIN_LONG_COLUMNS = [
    "property",
    "standard_unit",
    "standard_value",
    "range_min",
    "range_max",
    "property_value_raw",
    "property_unit_raw",
    "doi_or_file_id",
    "source_file",
    "source_row",
    "record_id",
    "superalloy_name",
    "sample_name",
    "composition_unit_raw",
    "composition_present_element_count",
    "composition_sum_numeric",
    "distinguishing_factor",
    "synthesis_and_processing_routes",
    "test_route_condition",
    "property_name_raw",
    "property_sourced_figure",
    "property_flags",
    "unit_conversion_note",
]


SUPERSCRIPT_MAP = str.maketrans(
    {
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
        "⁻": "-",
        "⁺": "+",
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "x",
        "·": " ",
        "∙": " ",
        "µ": "u",
        "μ": "u",
    }
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in EMPTY_STRINGS else text


def key_text(value: Any) -> str:
    text = clean(value).lower()
    return re.sub(r"\s+", " ", text)


def normalize_text(value: Any) -> str:
    return clean(value).translate(SUPERSCRIPT_MAP)


def normalize_unit(value: Any) -> str:
    text = normalize_text(value).lower()
    text = text.replace("per", "/")
    text = text.replace(" ", "")
    text = text.replace("(", "").replace(")", "")
    text = text.replace("²", "2").replace("^2", "2")
    text = text.replace("^-", "-")
    text = text.replace("−", "-")
    text = text.replace("m²", "m2")
    text = text.replace("mm²", "mm2")
    text = text.replace("n/mm^2", "n/mm2")
    text = text.replace("nmm-2", "n/mm2")
    text = text.replace("m.nm-2", "mnm-2")
    text = re.sub(r"\s+", "", text)
    return text


def parse_numeric(value: Any) -> tuple[float | None, int, str]:
    text = normalize_text(value)
    if not text:
        return None, 0, "missing"
    text = text.replace(",", "")
    text = re.sub(r"(?<=\d)\s*[-~]\s*(?=\d)", " to ", text)
    sci = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:x|\*)\s*10\s*\^?\s*([+-]?\d+)", text, flags=re.I)
    if sci:
        return float(sci.group(1)) * (10 ** int(sci.group(2))), 1, "scientific"
    tokens = re.findall(r"(?<![A-Za-z])[-+]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?", text)
    if not tokens:
        return None, 0, "no_numeric"
    try:
        first = float(tokens[0])
    except ValueError:
        return None, len(tokens), "parse_error"
    return first, len(tokens), "single" if len(tokens) == 1 else "range_or_multiple"


def standardize_value(property_name: str, value: Any, unit: Any) -> tuple[float | None, str, str, str]:
    numeric, _, parse_kind = parse_numeric(value)
    if numeric is None or not math.isfinite(float(numeric)):
        return None, "", "", "missing_or_unparseable_value"

    unit_norm = normalize_unit(unit)
    group = PROPERTY_SPECS[property_name]["group"]
    standard_unit = PROPERTY_SPECS[property_name]["unit"]

    factor: float | None = None
    note = ""
    if group == "stress":
        if unit_norm in {"mpa", "m.pa", "n/mm2", "mnm-2", "mn/m2"}:
            factor = 1.0
        elif unit_norm == "gpa":
            factor = 1000.0
            note = "GPa_to_MPa"
        elif unit_norm == "kpa":
            factor = 0.001
            note = "kPa_to_MPa"
        elif unit_norm == "pa":
            factor = 1e-6
            note = "Pa_to_MPa"
        elif unit_norm == "ksi":
            factor = 6.894757293
            note = "ksi_to_MPa"
        elif unit_norm in {"kg/mm2", "kgf/mm2", "kg/mm²"}:
            factor = 9.80665
            note = "kgf_mm2_to_MPa"
    elif group == "percent":
        if unit_norm in {"%", "percent", "pct.", "pct"}:
            factor = 1.0
    elif group == "length":
        if unit_norm == "mm":
            factor = 1.0
        elif unit_norm == "cm":
            factor = 10.0
            note = "cm_to_mm"
        elif unit_norm == "m":
            factor = 1000.0
            note = "m_to_mm"
        elif unit_norm in {"um", "micron", "microns"}:
            factor = 0.001
            note = "um_to_mm"
        elif unit_norm == "nm":
            factor = 1e-6
            note = "nm_to_mm"
        elif unit_norm in {"in", "in.", "inch", "inches"}:
            factor = 25.4
            note = "inch_to_mm"
    elif group == "strain_rate":
        if any(marker in unit_norm for marker in ["mpa", "pa/s", "n/s", "kn", "mm/s", "mm/min", "m/s"]):
            factor = None
        elif unit_norm in {"s-1", "s^-1", "/s", "1/s", "sec-1", "second-1"}:
            factor = 1.0
        elif unit_norm in {"min-1", "/min", "1/min"}:
            factor = 1.0 / 60.0
            note = "min^-1_to_s^-1"
        elif unit_norm in {"h-1", "hr-1", "/h", "1/h"}:
            factor = 1.0 / 3600.0
            note = "h^-1_to_s^-1"
        elif unit_norm in {"%/s", "percent/s", "pct/s"}:
            factor = 0.01
            note = "percent_per_s_to_s^-1"
        elif unit_norm in {"%/min", "percent/min", "pct/min"}:
            factor = 0.01 / 60.0
            note = "percent_per_min_to_s^-1"
        elif unit_norm in {"%/h", "percent/h", "pct/h"}:
            factor = 0.01 / 3600.0
            note = "percent_per_h_to_s^-1"

    if factor is None:
        return None, "", "", f"unit_mismatch:{unit_norm or '(missing unit)'}"
    converted = float(numeric) * factor
    if not math.isfinite(converted):
        return None, "", "", "non_finite_standard_value"
    return converted, standard_unit, note, parse_kind


def canonical_sheet_name(name: str, used: set[str]) -> str:
    safe = re.sub(r"[\[\]\:\*\?\/\\]", "_", name).strip()[:31] or "sheet"
    base = safe
    idx = 1
    while safe in used:
        suffix = f"_{idx}"
        safe = (base[: 31 - len(suffix)] + suffix)[:31]
        idx += 1
    used.add(safe)
    return safe


def write_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            if ws.max_row > 5000 or ws.max_column > 80:
                continue
            for col_cells in ws.columns:
                max_len = max((len(str(cell.value)) for cell in col_cells if cell.value is not None), default=8)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(max_len + 2, 10), 42)


def load_source(root: Path) -> pd.DataFrame:
    path = root / SOURCE_FILE
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_excel(path, dtype=str, keep_default_na=False)


def get_element_columns(df: pd.DataFrame) -> list[str]:
    start = list(df.columns).index("Co")
    end = list(df.columns).index("gauge length name")
    return list(df.columns[start:end])


def composition_metrics(row: pd.Series, element_cols: list[str]) -> tuple[int, float | str]:
    values = []
    for col in element_cols:
        numeric, _, _ = parse_numeric(row.get(col, ""))
        if numeric is not None:
            values.append(float(numeric))
    return len(values), round(sum(values), 8) if values else ""


def build_long_tables(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = load_source(root)
    element_cols = get_element_columns(df)
    property_names = list(PROPERTY_SPECS)
    has_any_property = pd.Series(False, index=df.index)
    for prop in property_names:
        has_any_property |= df[f"{prop} value"].map(clean) != ""

    rows = []
    for idx, row in df.iterrows():
        source_row = int(idx) + 2
        comp_count, comp_sum = composition_metrics(row, element_cols)
        identity_present = clean(row.get("steel name")) != "" or clean(row.get("full compositions")) != "" or comp_count > 0
        base = {
            "category": CATEGORY,
            "source_folder": SOURCE_FOLDER,
            "doi_or_file_id": clean(row.get("DOIs")),
            "source_file": SOURCE_FILE,
            "source_row": source_row,
            "record_id": f"steel:{source_row}",
            "superalloy_name": clean(row.get("steel name")),
            "sample_name": clean(row.get("sample name")),
            "composition_unit_raw": clean(row.get("composition unit")),
            "composition_unit_normalized": clean(row.get("composition unit")).lower(),
            "composition_present_element_count": comp_count,
            "composition_sum_numeric": comp_sum,
            "distinguishing_factor": clean(row.get("distinguishing factor")),
            "synthesis_and_processing_routes": clean(row.get("synthesis and processing routes")),
            "test_route_condition": clean(row.get("test route/condition")),
            "full_compositions_raw": clean(row.get("full compositions")),
        }
        for prop in property_names:
            raw_value = clean(row.get(f"{prop} value"))
            if raw_value == "":
                continue
            numeric_first, token_count, parse_kind = parse_numeric(raw_value)
            std_value, std_unit, conversion_note, std_parse_kind = standardize_value(prop, raw_value, row.get(f"{prop} unit"))
            flags = []
            if not identity_present:
                flags.append("missing_material_identity")
            if std_value is None:
                flags.append(conversion_note or "invalid_standard_value")
            property_row = {
                **base,
                "property_target_raw": prop,
                "property_target_canonical": prop,
                "property_name_raw": clean(row.get(f"{prop} name")) or prop,
                "property_value_raw": raw_value,
                "property_unit_raw": clean(row.get(f"{prop} unit")),
                "property_value_numeric_first": "" if numeric_first is None else numeric_first,
                "property_numeric_token_count": token_count,
                "property_numeric_parse_kind": std_parse_kind if std_value is not None else parse_kind,
                "property_standard_value": "" if std_value is None else std_value,
                "property_standard_unit": std_unit,
                "unit_conversion_note": conversion_note,
                "property_sourced_figure": clean(row.get(f"{prop} sourced figure")),
                "property_flags": ";".join(flags),
            }
            rows.append(property_row)

    long_df = pd.DataFrame(rows, columns=LONG_COLUMNS)
    identity_present = (
        (df["steel name"].map(clean) != "")
        | (df["full compositions"].map(clean) != "")
        | df.apply(lambda r: composition_metrics(r, element_cols)[0] > 0, axis=1)
    )
    valuable_source_rows = set((df.index[identity_present & has_any_property] + 2).astype(int))
    final_long = long_df[long_df["source_row"].isin(valuable_source_rows)].copy()
    final_records = df.loc[[row - 2 for row in sorted(valuable_source_rows)]].copy()
    final_records.insert(0, "record_id", [f"steel:{row}" for row in sorted(valuable_source_rows)])
    return long_df, final_long, final_records


def annotated_units(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    data = df.copy()
    data["统计口径"] = scope
    data["性能"] = data["property_target_canonical"].map(clean)
    data["原始单位"] = data["property_unit_raw"].map(clean)
    data["标准单位"] = data["property_standard_unit"].map(clean)
    data["性能值"] = data["property_value_raw"].map(clean)
    data["标准化数值"] = pd.to_numeric(data["property_standard_value"], errors="coerce")
    data["单位是否匹配性能"] = data.apply(
        lambda r: "yes"
        if clean(r["标准单位"]) == PROPERTY_SPECS.get(clean(r["性能"]), {}).get("unit", "")
        and pd.notna(r["标准化数值"])
        and math.isfinite(float(r["标准化数值"]))
        else "no",
        axis=1,
    )
    data["单位规则类型"] = data["性能"].map(lambda p: PROPERTY_SPECS.get(p, {}).get("group", "no_rule"))
    data["单位规则说明"] = data["性能"].map(lambda p: PROPERTY_SPECS.get(p, {}).get("note", "No rule configured."))
    return data


def value_distribution(valid_df: pd.DataFrame) -> pd.DataFrame:
    data = valid_df[valid_df["单位是否匹配性能"] == "yes"].copy()
    grouped = (
        data.groupby(["统计口径", "性能", "标准单位"], dropna=False)
        .agg(
            数据量=("标准化数值", "count"),
            最小值=("标准化数值", "min"),
            最大值=("标准化数值", "max"),
            平均值=("标准化数值", "mean"),
            标准差=("标准化数值", "std"),
        )
        .reset_index()
    )
    grouped["标准差"] = grouped["标准差"].fillna(0)
    for col in ["最小值", "最大值", "平均值", "标准差"]:
        grouped[col] = grouped[col].astype(float).round(6)
    return grouped.sort_values(["统计口径", "性能", "数据量"], ascending=[True, True, False])


def valid_raw_unit_frequency(valid_df: pd.DataFrame) -> pd.DataFrame:
    data = valid_df[(valid_df["性能值"] != "") & (valid_df["单位是否匹配性能"] == "yes")].copy()
    data["原始单位"] = data["原始单位"].replace("", "(missing unit)")
    grouped = (
        data.groupby(["统计口径", "性能", "原始单位"], dropna=False)
        .agg(
            频次=("record_id", "count"),
            涉及样品记录数=("record_id", "nunique"),
            映射后的标准单位=("标准单位", lambda x: "; ".join(sorted({clean(v) for v in x if clean(v)})) or "(not standardized)"),
        )
        .reset_index()
    )
    totals = grouped.groupby(["统计口径", "性能"])["频次"].transform("sum")
    grouped["占该性能比例(%)"] = (grouped["频次"] / totals * 100).round(2)
    return grouped[["统计口径", "性能", "原始单位", "频次", "占该性能比例(%)", "涉及样品记录数", "映射后的标准单位"]].sort_values(
        ["统计口径", "性能", "频次"], ascending=[True, True, False]
    )


def invalid_unit_frequency(valid_df: pd.DataFrame) -> pd.DataFrame:
    data = valid_df[(valid_df["性能值"] != "") & (valid_df["单位是否匹配性能"] == "no")].copy()
    data["原始单位"] = data["原始单位"].replace("", "(missing unit)")
    data["标准单位"] = data["标准单位"].replace("", "(not standardized)")
    grouped = (
        data.groupby(["统计口径", "性能", "原始单位", "标准单位", "单位规则类型", "单位规则说明"], dropna=False)
        .agg(频次=("record_id", "count"), 涉及样品记录数=("record_id", "nunique"))
        .reset_index()
    )
    return grouped.sort_values(["统计口径", "性能", "频次"], ascending=[True, True, False])


def validation_summary(valid_df: pd.DataFrame) -> pd.DataFrame:
    data = valid_df[valid_df["性能值"] != ""].copy()
    grouped = (
        data.groupby(["统计口径", "性能"], dropna=False)
        .agg(
            有性能值总数=("record_id", "count"),
            单位匹配数量=("单位是否匹配性能", lambda x: int((x == "yes").sum())),
            单位不匹配数量=("单位是否匹配性能", lambda x: int((x == "no").sum())),
            原始单位种类数=("原始单位", lambda x: len({clean(v) or "(missing unit)" for v in x})),
        )
        .reset_index()
    )
    grouped["单位匹配比例(%)"] = (grouped["单位匹配数量"] / grouped["有性能值总数"] * 100).round(2)
    return grouped.sort_values(["统计口径", "单位匹配比例(%)", "有性能值总数"], ascending=[True, False, False])


def unit_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"性能": prop, "单位规则类型": spec["group"], "单位规则说明": spec["note"]}
            for prop, spec in PROPERTY_SPECS.items()
        ]
    )


def export_unit_statistics(all_long: pd.DataFrame, final_long: pd.DataFrame, out_dir: Path, root: Path) -> None:
    combined = pd.concat(
        [annotated_units(all_long, "全部清洗后抽取结果"), annotated_units(final_long, "最终有价值数据")],
        ignore_index=True,
    )
    distribution = value_distribution(combined)
    valid_units = valid_raw_unit_frequency(combined)
    invalid_units = invalid_unit_frequency(combined)
    summary = validation_summary(combined)
    rules = unit_rules()

    distribution.to_csv(out_dir / "property_value_distribution_statistics_valid_units.csv", index=False, encoding="utf-8-sig")
    valid_units.to_csv(out_dir / "property_valid_raw_unit_frequency_statistics.csv", index=False, encoding="utf-8-sig")
    invalid_units.to_csv(out_dir / "property_invalid_unit_candidates.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "property_unit_validation_summary.csv", index=False, encoding="utf-8-sig")
    rules.to_csv(out_dir / "property_unit_validation_rules.csv", index=False, encoding="utf-8-sig")

    target = root / "property_distribution_and_unit_statistics_valid_units.xlsx"
    sheets = {
        "value_distribution_valid": distribution,
        "valid_raw_unit_frequency": valid_units,
        "invalid_unit_candidates": invalid_units,
        "validation_summary": summary,
        "unit_rules": rules,
    }
    write_excel(target, sheets)
    shutil.copy2(target, out_dir / target.name)


def valid_final_rows(final_long: pd.DataFrame) -> pd.DataFrame:
    data = annotated_units(final_long, "最终有价值数据")
    valid = data[(data["单位是否匹配性能"] == "yes") & data["标准化数值"].notna()].copy()
    valid = valid[valid["标准化数值"].map(lambda x: math.isfinite(float(x)))]
    return valid


def export_origin_top_properties(final_long: pd.DataFrame, out_dir: Path, root: Path) -> None:
    valid = valid_final_rows(final_long)
    unit_counts = (
        valid.groupby(["性能", "标准单位"], dropna=False)
        .agg(data_count_before_range_filter=("record_id", "count"), sample_record_count_before=("record_id", "nunique"))
        .reset_index()
        .sort_values(["性能", "data_count_before_range_filter"], ascending=[True, False])
    )
    selected_units = unit_counts.groupby("性能", as_index=False).first().rename(
        columns={"性能": "property", "标准单位": "selected_standard_unit"}
    )
    top = selected_units.sort_values("data_count_before_range_filter", ascending=False).head(8).copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    selected_pairs = set(zip(top["property"], top["selected_standard_unit"]))

    selected = valid[valid.apply(lambda r: (r["性能"], r["标准单位"]) in selected_pairs, axis=1)].copy()
    selected["property"] = selected["性能"]
    selected["standard_unit"] = selected["标准单位"]
    selected["standard_value"] = selected["标准化数值"].astype(float)
    selected["range_min"] = selected["property"].map(lambda p: PROPERTY_SPECS[p]["range"][0])
    selected["range_max"] = selected["property"].map(lambda p: PROPERTY_SPECS[p]["range"][1])
    selected["range_filter_pass"] = selected.apply(
        lambda r: float(r["range_min"]) <= float(r["standard_value"]) <= float(r["range_max"]),
        axis=1,
    )
    selected["range_filter_reason"] = selected.apply(
        lambda r: "pass"
        if r["range_filter_pass"]
        else f"outside_common_range_[{r['range_min']}, {r['range_max']}]",
        axis=1,
    )
    filtered = selected[selected["range_filter_pass"]].copy()
    outliers = selected[~selected["range_filter_pass"]].copy()

    for col in ORIGIN_LONG_COLUMNS:
        if col not in filtered.columns:
            filtered[col] = ""
        if col not in outliers.columns:
            outliers[col] = ""
    origin_long = filtered[ORIGIN_LONG_COLUMNS].sort_values(["property", "standard_value"]).reset_index(drop=True)
    outliers_out = outliers[ORIGIN_LONG_COLUMNS + ["range_filter_reason"]].sort_values(["property", "standard_value"]).reset_index(drop=True)

    wide = pd.DataFrame()
    for _, row in top.iterrows():
        label = f"{row['property']} ({row['selected_standard_unit']})"
        values = origin_long.loc[
            (origin_long["property"] == row["property"]) & (origin_long["standard_unit"] == row["selected_standard_unit"]),
            "standard_value",
        ].reset_index(drop=True)
        wide[label] = values

    stats = (
        origin_long.groupby(["property", "standard_unit"], dropna=False)
        .agg(
            data_count_after_range_filter=("standard_value", "count"),
            min_value=("standard_value", "min"),
            max_value=("standard_value", "max"),
            mean_value=("standard_value", "mean"),
            std_value=("standard_value", "std"),
        )
        .reset_index()
    )
    stats["std_value"] = stats["std_value"].fillna(0)
    outlier_counts = outliers_out.groupby(["property", "standard_unit"], dropna=False).size().reset_index(name="removed_by_range_filter")
    top = (
        top.merge(stats.rename(columns={"standard_unit": "selected_standard_unit"}), on=["property", "selected_standard_unit"], how="left")
        .merge(outlier_counts.rename(columns={"standard_unit": "selected_standard_unit"}), on=["property", "selected_standard_unit"], how="left")
    )
    top["removed_by_range_filter"] = top["removed_by_range_filter"].fillna(0).astype(int)
    top["retention_after_range_filter_percent"] = (
        top["data_count_after_range_filter"] / top["data_count_before_range_filter"] * 100
    ).round(2)
    top["range_rule"] = top.apply(lambda r: str(PROPERTY_SPECS[r["property"]]["range"]), axis=1)

    target = root / "origin_top8_property_distribution_data_range_filtered.xlsx"
    sheets = {
        "summary_top8_range": top,
        "origin_long_filtered": origin_long,
        "origin_wide_filtered": wide,
        "removed_outliers": outliers_out,
    }
    used = set(sheets)
    for _, row in top.iterrows():
        prop = row["property"]
        unit = row["selected_standard_unit"]
        sheet = canonical_sheet_name(f"{int(row['rank'])}_{prop}", used)
        sheets[sheet] = origin_long[(origin_long["property"] == prop) & (origin_long["standard_unit"] == unit)].copy()
    write_excel(target, sheets)
    shutil.copy2(target, out_dir / target.name)

    top.to_csv(out_dir / "origin_top8_property_distribution_summary_range_filtered.csv", index=False, encoding="utf-8-sig")
    origin_long.to_csv(out_dir / "origin_top8_property_distribution_long_range_filtered.csv", index=False, encoding="utf-8-sig")
    wide.to_csv(out_dir / "origin_top8_property_distribution_wide_range_filtered.csv", index=False, encoding="utf-8-sig")
    outliers_out.to_csv(out_dir / "origin_top8_property_distribution_removed_outliers.csv", index=False, encoding="utf-8-sig")


def export_retention_table(source_rows: int, all_long: pd.DataFrame, final_long: pd.DataFrame, root: Path, out_dir: Path) -> None:
    valid = valid_final_rows(final_long)
    rows = []
    for prop in PROPERTY_SPECS:
        raw_count = int((all_long["property_target_canonical"] == prop).sum())
        sub = valid[valid["性能"] == prop].copy()
        if not sub.empty:
            low, high = PROPERTY_SPECS[prop]["range"]
            sub = sub[(sub["标准化数值"].astype(float) >= low) & (sub["标准化数值"].astype(float) <= high)]
        retained = int(sub["record_id"].nunique()) if not sub.empty else 0
        value_count = int(len(sub))
        rows.append(
            {
                "类别": prop,
                " 输入记录": raw_count,
                "有价值记录": retained,
                " 保留率": round(retained / raw_count * 100, 2) if raw_count else 0,
                "有价值性能值": value_count,
            }
        )
    rows.insert(
        0,
        {
            "类别": "all_source_rows",
            " 输入记录": source_rows,
            "有价值记录": int(final_long["record_id"].nunique()),
            " 保留率": round(final_long["record_id"].nunique() / source_rows * 100, 2) if source_rows else 0,
            "有价值性能值": int(len(final_long)),
        },
    )
    retention = pd.DataFrame(rows)
    target = root / "property_level_retention_table.xlsx"
    write_excel(target, {"property_retention": retention})
    shutil.copy2(target, out_dir / target.name)
    retention.to_csv(out_dir / "property_level_retention_table.csv", index=False, encoding="utf-8-sig")


def pearson(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 3 or x.nunique(dropna=True) < 2 or y.nunique(dropna=True) < 2:
        return float("nan")
    return float(x.corr(y, method="pearson"))


def spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 3 or x.nunique(dropna=True) < 2 or y.nunique(dropna=True) < 2:
        return float("nan")
    return float(x.rank().corr(y.rank(), method="pearson"))


def pair_note(a: str, b: str) -> str:
    normalized = {tuple(sorted(k)): v for k, v in PAIR_NOTES.items()}
    return normalized.get(tuple(sorted([a, b])), "Exploratory pair; interpret with matched processing and testing context.")


def selected_property_rows_for_pairs(final_long: pd.DataFrame) -> pd.DataFrame:
    data = valid_final_rows(final_long)
    data = data.copy()
    data["property"] = data["性能"]
    data["standard_unit"] = data["标准单位"]
    data["standard_value"] = data["标准化数值"].astype(float)
    frames = []
    for prop, spec in PROPERTY_SPECS.items():
        sub = data[(data["property"] == prop) & (data["standard_unit"] == spec["unit"])].copy()
        low, high = spec["range"]
        sub = sub[(sub["standard_value"] >= low) & (sub["standard_value"] <= high)]
        frames.append(sub)
    selected = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    selected = selected[(selected["doi_or_file_id"].map(clean) != "") & (selected["superalloy_name"].map(clean) != "")]
    selected["strict_key"] = selected.apply(
        lambda r: "|".join(
            [
                key_text(r.get("doi_or_file_id", "")),
                key_text(r.get("superalloy_name", "")),
                key_text(r.get("sample_name", "")),
                key_text(r.get("distinguishing_factor", "")),
                key_text(r.get("synthesis_and_processing_routes", "")),
            ]
        ),
        axis=1,
    )
    selected["relaxed_key"] = selected.apply(
        lambda r: "|".join(
            [
                key_text(r.get("doi_or_file_id", "")),
                key_text(r.get("superalloy_name", "")),
                key_text(r.get("synthesis_and_processing_routes", "")),
            ]
        ),
        axis=1,
    )
    return selected


def collapse_property_per_key(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    meta_cols = [
        "doi_or_file_id",
        "superalloy_name",
        "sample_name",
        "distinguishing_factor",
        "synthesis_and_processing_routes",
        "test_route_condition",
        "source_file",
        "source_row",
        "record_id",
        "property_value_raw",
        "property_unit_raw",
        "property_sourced_figure",
    ]
    grouped_rows = []
    for (key, prop), group in df.groupby([key_col, "property"], dropna=False):
        values = group["standard_value"].astype(float)
        first = group.iloc[0]
        row = {
            key_col: key,
            "property": prop,
            "value": float(values.median()),
            "value_mean": float(values.mean()),
            "value_count_for_key": int(len(values)),
            "standard_unit": first["standard_unit"],
        }
        for col in meta_cols:
            row[col] = first.get(col, "")
        grouped_rows.append(row)
    return pd.DataFrame(grouped_rows)


def build_pair_table(collapsed: pd.DataFrame, key_col: str, prop_a: str, prop_b: str) -> pd.DataFrame:
    a = collapsed[collapsed["property"] == prop_a].copy()
    b = collapsed[collapsed["property"] == prop_b].copy()
    merged = a.merge(b, on=key_col, suffixes=("_x", "_y"))
    if merged.empty:
        return merged
    return pd.DataFrame(
        {
            "match_level": "strict" if key_col == "strict_key" else "relaxed",
            "pair": f"{prop_a} vs {prop_b}",
            "match_key": merged[key_col],
            "doi_or_file_id": merged["doi_or_file_id_x"].combine_first(merged["doi_or_file_id_y"]),
            "superalloy_name": merged["superalloy_name_x"].combine_first(merged["superalloy_name_y"]),
            "sample_name_x": merged["sample_name_x"],
            "sample_name_y": merged["sample_name_y"],
            "distinguishing_factor_x": merged["distinguishing_factor_x"],
            "distinguishing_factor_y": merged["distinguishing_factor_y"],
            "synthesis_and_processing_routes_x": merged["synthesis_and_processing_routes_x"],
            "synthesis_and_processing_routes_y": merged["synthesis_and_processing_routes_y"],
            "test_route_condition_x": merged["test_route_condition_x"],
            "test_route_condition_y": merged["test_route_condition_y"],
            "property_x": prop_a,
            "value_x": merged["value_x"],
            "unit_x": merged["standard_unit_x"],
            "property_y": prop_b,
            "value_y": merged["value_y"],
            "unit_y": merged["standard_unit_y"],
            "source_file_x": merged["source_file_x"],
            "source_row_x": merged["source_row_x"],
            "record_id_x": merged["record_id_x"],
            "raw_value_x": merged["property_value_raw_x"],
            "raw_unit_x": merged["property_unit_raw_x"],
            "source_file_y": merged["source_file_y"],
            "source_row_y": merged["source_row_y"],
            "record_id_y": merged["record_id_y"],
            "raw_value_y": merged["property_value_raw_y"],
            "raw_unit_y": merged["property_unit_raw_y"],
        }
    )


def summarize_pair(pair_df: pd.DataFrame, prop_a: str, prop_b: str, match_level: str) -> dict[str, Any]:
    spec_a = PROPERTY_SPECS[prop_a]
    spec_b = PROPERTY_SPECS[prop_b]
    if pair_df.empty:
        return {
            "match_level": match_level,
            "property_x": prop_a,
            "unit_x": spec_a["unit"],
            "property_y": prop_b,
            "unit_y": spec_b["unit"],
            "matched_count": 0,
            "pearson_r": "",
            "spearman_r": "",
            "recommended_plot_x": prop_a,
            "recommended_plot_y": prop_b,
            "reason": pair_note(prop_a, prop_b),
        }
    p = pearson(pair_df["value_x"].astype(float), pair_df["value_y"].astype(float))
    s = spearman(pair_df["value_x"].astype(float), pair_df["value_y"].astype(float))
    return {
        "match_level": match_level,
        "property_x": prop_a,
        "unit_x": spec_a["unit"],
        "property_y": prop_b,
        "unit_y": spec_b["unit"],
        "matched_count": int(len(pair_df)),
        "pearson_r": round(p, 4) if not math.isnan(p) else "",
        "spearman_r": round(s, 4) if not math.isnan(s) else "",
        "recommended_plot_x": prop_a,
        "recommended_plot_y": prop_b,
        "reason": pair_note(prop_a, prop_b),
    }


def export_pair_correlations(final_long: pd.DataFrame, out_dir: Path, root: Path) -> None:
    selected = selected_property_rows_for_pairs(final_long)
    all_summaries = []
    pair_tables = {}
    pair_properties = list(PROPERTY_SPECS)
    for key_col in ["strict_key", "relaxed_key"]:
        collapsed = collapse_property_per_key(selected, key_col)
        match_level = "strict" if key_col == "strict_key" else "relaxed"
        for prop_a, prop_b in itertools.combinations(pair_properties, 2):
            pair_df = build_pair_table(collapsed, key_col, prop_a, prop_b)
            all_summaries.append(summarize_pair(pair_df, prop_a, prop_b, match_level))
            if len(pair_df) >= 20:
                pair_tables[(match_level, prop_a, prop_b)] = pair_df

    summary = pd.DataFrame(all_summaries).sort_values(["match_level", "matched_count"], ascending=[True, False]).reset_index(drop=True)
    recommended = summary[
        (summary["matched_count"] >= 50)
        & summary["reason"].str.contains("Strength|ductility|Rate|Consistency|Uniform", case=False, regex=True)
    ].copy()
    recommended = recommended.sort_values(["match_level", "matched_count"], ascending=[True, False])

    target = root / "property_pair_correlation_candidates.xlsx"
    selected_for_workbook = selected.head(50000).copy()
    sheets: dict[str, pd.DataFrame] = {
        "pair_summary_all": summary,
        "recommended_pairs": recommended,
        "selected_property_rows": selected_for_workbook,
    }
    used = set(sheets)
    for (match_level, prop_a, prop_b), df in sorted(pair_tables.items(), key=lambda item: (item[0][0], -len(item[1]))):
        sheet = canonical_sheet_name(f"{match_level}_{prop_a[:8]}_{prop_b[:8]}", used)
        sheets[sheet] = df.head(5000).copy()
    write_excel(target, sheets)
    shutil.copy2(target, out_dir / target.name)

    summary.to_csv(out_dir / "property_pair_correlation_summary.csv", index=False, encoding="utf-8-sig")
    recommended.to_csv(out_dir / "property_pair_correlation_recommended_pairs.csv", index=False, encoding="utf-8-sig")
    for (match_level, prop_a, prop_b), df in pair_tables.items():
        if len(df) >= 50:
            name = re.sub(r"[^A-Za-z0-9]+", "_", f"property_pair_{match_level}_{prop_a}_vs_{prop_b}").strip("_")
            df.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    tables_dir = root / "tables"
    final_tables_dir = root / "final_valuable_dataset" / "tables"
    figure_tables_dir = root / "paper_diversity_figures" / "tables"
    for folder in [tables_dir, final_tables_dir, figure_tables_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    if mode == "pairs-only":
        final_long_path = final_tables_dir / "final_ext-1_steel_tensile_mechanical_valuable_properties_long.csv"
        final_long = pd.read_csv(final_long_path, dtype=str, keep_default_na=False)
        export_pair_correlations(final_long, figure_tables_dir, root)
        print(f"Wrote pair correlation outputs to: {root}")
        return

    all_long, final_long, final_records = build_long_tables(root)
    all_long.to_csv(tables_dir / "ext-1_steel_tensile_mechanical_properties_long.csv", index=False, encoding="utf-8-sig")
    final_long.to_csv(final_tables_dir / "final_ext-1_steel_tensile_mechanical_valuable_properties_long.csv", index=False, encoding="utf-8-sig")
    final_records.to_csv(final_tables_dir / "final_ext-1_steel_tensile_mechanical_valuable_records.csv", index=False, encoding="utf-8-sig")

    write_excel(tables_dir / "ext-1_steel_tensile_mechanical_properties_long.xlsx", {"properties_long": all_long})
    write_excel(final_tables_dir / "final_ext-1_steel_tensile_mechanical_valuable_properties_long.xlsx", {"properties_long": final_long})
    write_excel(final_tables_dir / "final_ext-1_steel_tensile_mechanical_valuable_records.xlsx", {"valuable_records": final_records})

    export_unit_statistics(all_long, final_long, figure_tables_dir, root)
    export_origin_top_properties(final_long, figure_tables_dir, root)
    export_retention_table(len(load_source(root)), all_long, final_long, root, figure_tables_dir)
    export_pair_correlations(final_long, figure_tables_dir, root)

    print(f"Wrote steel extraction outputs to: {root}")
    print(f"All property rows: {len(all_long)}")
    print(f"Final valuable property rows: {len(final_long)}")
    print(f"Final valuable records: {final_long['record_id'].nunique()}")


if __name__ == "__main__":
    main()
