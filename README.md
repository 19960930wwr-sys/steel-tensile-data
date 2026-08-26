# Steel Extractor

OpenAI-compatible literature extraction workflow for steel tensile-property records.

## What this repository contains

- Prompt templates for the two-stage LLM extraction flow.
- A reusable Python package for parsing article context, calling an OpenAI-compatible model, repairing malformed output, and filtering unsupported records.
- A steel-specific output schema that matches the released dataset format.
- A minimal example input bundle for local smoke tests.

## What this repository does not contain

- Article retrieval or bulk download code.
- Private API keys or endpoint credentials.
- Local corpus files from the research workspace.

## Workflow

1. Parse an article bundle into a unified context containing text, tables, figure captions, and source blocks.
2. Call the model once to enumerate explicit property evidence.
3. Call the model a second time to integrate that evidence into steel material records.
4. Repair malformed outputs when needed.
5. Remove unsupported or duplicate records and export JSON/CSV/XLSX outputs.

The implementation follows the steel workflow used in the accompanying manuscript:

- The first stage extracts property evidence only.
- The second stage creates final records with material identity, composition, processing route, testing context, and the six target variables.
- `strain rate` and `gauge length` are treated as testing/specimen descriptors.

## Installation

```bash
pip install -r requirements.txt
```

## Environment variables

Set the API key before running:

```powershell
$env:STEEL_LLM_API_KEY = "your_api_key"
```

Optional variables:

- `STEEL_LLM_BASE_URL`
- `STEEL_LLM_MODEL`

If the model name starts with `qwen`, the code uses the DashScope OpenAI-compatible endpoint by default.

## Example usage

```bash
python -m steel_extractor.cli ^
  --input examples/example_article.json ^
  --output-dir outputs ^
  --model qwen-plus ^
  --material-type steel
```

The CLI accepts a single file or a directory of files with these extensions:

- `.json`
- `.xml`
- `.html`
- `.txt`

## Prompt and schema files

- `prompts/stage1_property_evidence.txt`
- `prompts/stage2_material_record.txt`
- `prompts/format_repair.txt`
- `schema/output_pattern.json`

## Output

For each input file, the pipeline writes:

- `*_records.json`
- `*_evidence.json`
- `*_records.csv`
- `*_records.xlsx` when pandas/openpyxl are available

## Notes

- The code is designed for OpenAI-compatible chat-completion APIs.
- The model call explicitly disables Qwen thinking mode with `enable_thinking=False`.
- The public repository should keep API keys, private article files, and internal paths out of version control.

