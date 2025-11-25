
# VSCode Local Runner — Operational Profile Generator

This setup lets you run the profile generator **locally in VSCode** (macOS/Windows/Linux) with:
- `.env` file support (loads `OPENAI_API_KEY` and optional AWS settings)
- Optional **S3 uploads** via your local AWS CLI profile
- **Single-call** or **chunked** generation

## Files
- `local_profile_builder.py` — unified script with both modes
- `requirements-local.txt` — adds `python-dotenv` for .env
- `.env.example` — sample environment file
- `launch.json` / `tasks.json` — copy into `.vscode/` for one-click run/debug
- `sample_enterprises.csv` — starter CSV
- `operational_profile_template.json` — **provide your outline** (same schema you’ve been using)

## Quick Start
```bash
# 1) Install deps
pip install -r requirements-local.txt

# 2) Create a .env from the example and set your OpenAI key
cp .env.example .env
# edit .env and set OPENAI_API_KEY=...

# 3) Run (single-call, local only; no S3 upload)
python local_profile_builder.py \
  --csv ./sample_enterprises.csv \
  --template ./operational_profile_template.json \
  --outdir ./out \
  --model gpt-5-pro \
  --include-word --include-ppt --include-json \
  --no-s3
```

## Chunked Mode (recommended for long reports)
```bash
python local_profile_builder.py \
  --csv ./sample_enterprises.csv \
  --template ./operational_profile_template.json \
  --outdir ./out \
  --model gpt-5-pro \
  --chunked --granularity top \
  --include-word --include-ppt --include-json \
  --no-s3
```

## Optional S3 Uploads from Local
Use your AWS CLI profile (e.g., `default`) and provide bucket/prefix:
```bash
python local_profile_builder.py \
  --csv ./sample_enterprises.csv \
  --template ./operational_profile_template.json \
  --outdir ./out \
  --model gpt-5-pro \
  --chunked --granularity top \
  --include-word --include-ppt --include-json \
  --s3-bucket your-bucket \
  --s3-prefix profiles/local \
  --aws-profile default
```

**.env example:**
```
OPENAI_API_KEY=YOUR_API_KEY
AWS_PROFILE=default
AWS_REGION=us-east-1
S3_BUCKET=your-bucket
S3_PREFIX=profiles/local
OPENAI_MODEL=gpt-5-pro
OPENAI_FALLBACK_MODEL=gpt-4.1
```

## VSCode
1. Copy `launch.json` and `tasks.json` into a `.vscode/` folder in your workspace.
2. Open **Run and Debug** panel, choose a configuration:
   - **Local: Single-Call (No S3)**
   - **Local: Chunked (Top, No S3)**
   - **Local: Chunked (Top, S3 using AWS Profile)**
3. Hit **Run**.

## Notes
- Place `operational_profile_template.json` in the project root (or supply a path).
- For very large sections, switch `--granularity leaf` to maximize chunking.
- To resume, simply re-run—partials are saved per enterprise directory.
- If you need stricter schema enforcement, add a JSON Schema validator.

