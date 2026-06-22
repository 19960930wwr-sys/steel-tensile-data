from pathlib import Path

import pandas as pd


def main() -> None:
    root = Path(r"E:\本人信息\博士后\Papers\steel_data_extraction\paper_diversity_figures\tables")
    invalid = pd.read_csv(root / "property_invalid_unit_candidates.csv")
    valid = pd.read_csv(root / "property_valid_raw_unit_frequency_statistics.csv")
    props = [
        "yield strength",
        "tensile strength",
        "total elongation",
        "uniform elongation",
        "strain rate",
        "gauge length",
    ]

    for prop in props:
        print("PROP", prop)
        valid_units = valid[valid["性能"] == prop]["原始单位"].drop_duplicates().astype(str).tolist()
        invalid_units = invalid[invalid["性能"] == prop]["原始单位"].drop_duplicates().astype(str).tolist()
        valid_text = ", ".join(u.encode("unicode_escape").decode("ascii") for u in valid_units[:20])
        invalid_text = ", ".join(u.encode("unicode_escape").decode("ascii") for u in invalid_units[:20])
        print(" valid:", valid_text)
        print(" invalid:", invalid_text)
        print("---")


if __name__ == "__main__":
    main()
