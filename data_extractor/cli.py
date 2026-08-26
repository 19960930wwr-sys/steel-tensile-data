from __future__ import annotations

import argparse
import os
from pathlib import Path

from .pipeline import run_batch
from .schema import DEFAULT_ACTIONS, STEEL_TENSILE_TARGETS


def parse_args():
    parser = argparse.ArgumentParser(description="Steel tensile-property extraction workflow")
    parser.add_argument("--input", required=True, help="Input file or directory")
    parser.add_argument("--output-dir", required=True, help="Directory for extracted outputs")
    parser.add_argument("--api-key", default=os.getenv("STEEL_LLM_API_KEY", ""), help="LLM API key")
    parser.add_argument(
        "--base-url",
        default=os.getenv("STEEL_LLM_BASE_URL", ""),
        help="Optional OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("STEEL_LLM_MODEL", "qwen-plus"),
        help="Model name, e.g. qwen-plus",
    )
    parser.add_argument("--material-type", default="steel", help="Material type label")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=STEEL_TENSILE_TARGETS,
        help="Target properties",
    )
    parser.add_argument(
        "--actions",
        nargs="+",
        default=DEFAULT_ACTIONS,
        help="Allowed process-action vocabulary",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Missing API key. Set STEEL_LLM_API_KEY or pass --api-key.")

    outputs = run_batch(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        api_key=args.api_key,
        model_name=args.model,
        material_type=args.material_type,
        targets=args.targets,
        actions=args.actions,
        base_url=args.base_url or None,
    )

    for out in outputs:
        print(out["json"])


if __name__ == "__main__":
    main()

