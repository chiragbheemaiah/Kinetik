# Batch Operational Profile Generation System

Complete system for generating detailed operational profiles for multiple enterprises in parallel with advanced features.

## Overview

This system generates comprehensive 70-page equivalent operational profiles for enterprises including:
- Detailed JSON profiles with 14 major sections covering vision, revenue, organization, workforce, technology, data, governance, etc.
- Word documents with auto-generated Table of Contents
- CSV exports of embedded revenue/data tables
- Structured logging and progress tracking

## System Components

### Core Scripts

1. **`profile_builder.py`** - Main profile generation engine
   - Uses OpenAI GPT-4o to generate detailed consulting-grade content
   - Configurable word counts per section via `section_config.json`
   - Retry logic with compact mode fallback for API limits
   - Parameterized for any enterprise via `--enterprise` flag

2. **`create_word_doc.py`** - Word document generator
   - Converts JSON profiles to formatted Word documents
   - Auto-generates Table of Contents
   - Renders list-of-dicts as proper Word tables
   - Exports embedded tables to CSV files

3. **`batch_generate.py`** - Batch orchestration system
   - Processes multiple enterprises from `Accounts.csv`
   - Parallel processing with configurable workers
   - Rate limiting for API quota management
   - Incremental resume (skip already-processed enterprises)
   - Structured JSON logging per enterprise

### Configuration Files

- **`Accounts.csv`** - Enterprise list with metadata (name, industry, revenue, employees, business units)
- **`section_config.json`** - Word count targets and special instructions per section
- **`operational_profile_template.json`** - JSON structure template with 14 sections
- **`.env`** - Contains `OPENAI_API_KEY`

## Quick Start

### Single Enterprise Generation

Generate a profile for one company:

```bash
source venv/bin/activate

# Use default (Citigroup Inc.)
python3 profile_builder.py

# Specify custom enterprise
python3 profile_builder.py --enterprise "Airbus" --output-dir outputs/airbus

# Generate Word document
python3 create_word_doc.py --input outputs/airbus/profile_detailed.json \
                            --output outputs/airbus/airbus_profile.docx \
                            --export-csv-dir outputs/airbus/tables
```

### Batch Processing

Process multiple enterprises from `Accounts.csv`:

```bash
source venv/bin/activate

# Process first 3 enterprises (sequential)
python3 batch_generate.py --limit 3

# Process all enterprises with 2 parallel workers
python3 batch_generate.py --workers 2 --rate-limit 5

# Force regeneration of existing profiles
python3 batch_generate.py --force --limit 5

# Custom output directory
python3 batch_generate.py --out-dir custom_batch_outputs --limit 10
```

## Advanced Features

### 1. Parallel Processing

Run multiple profile generations concurrently to speed up batch jobs:

```bash
# 4 workers with 10-second delay between job starts
python3 batch_generate.py --workers 4 --rate-limit 10
```

**Recommendations:**
- Start with `--workers 2` to test
- Use `--rate-limit 5-10` to avoid API rate limits
- Monitor OpenAI API usage dashboard

### 2. Incremental Resume

Skip already-processed enterprises to resume interrupted batches:

```bash
# First run - processes Airbus, American Express, AT&T
python3 batch_generate.py --limit 3

# Second run - automatically skips first 3, processes next 2
python3 batch_generate.py --limit 5

# Force regenerate all
python3 batch_generate.py --limit 5 --force
```

### 3. Custom Output Directory

Organize outputs by batch, date, or client:

```bash
# Dated batch
python3 batch_generate.py --out-dir batch_outputs/2025-11-09 --limit 10

# Client-specific
python3 batch_generate.py --out-dir client_deliverables/acme_corp --limit 5
```

### 4. Structured Logging

Each enterprise gets:
- **Global log**: `batch_outputs/batch.log` (all enterprises)
- **Per-enterprise log**: `batch_outputs/<enterprise>/process_log.json`
- **Batch summary**: `batch_outputs/batch_summary.json`

Example `process_log.json`:
```json
{
  "enterprise": "Airbus",
  "slug": "airbus",
  "start_time": "2025-11-09T14:23:10.123456",
  "status": "success",
  "json_path": "/path/to/profile_detailed.json",
  "docx_path": "/path/to/airbus_operational_profile.docx",
  "end_time": "2025-11-09T15:45:32.654321",
  "duration_seconds": 4942.5
}
```

## Output Structure

```
batch_outputs/
├── batch.log                          # Global processing log
├── batch_summary.json                 # Batch-level summary with stats
├── airbus/
│   ├── profile_detailed.json          # Full JSON profile
│   ├── airbus_operational_profile.docx # Word document with TOC
│   ├── process_log.json               # Processing metadata
│   └── tables/
│       ├── 2_revenue_reporting_2_1_revenue_by_business_segment_table.csv
│       └── 2_revenue_reporting_2_2_revenue_by_line_of_business_table.csv
├── american_express/
│   ├── profile_detailed.json
│   ├── american_express_operational_profile.docx
│   ├── process_log.json
│   └── tables/
└── ...
```

## Customization

### Adjusting Word Counts

Edit `section_config.json`:

```json
{
  "default_word_count": "800-1200",
  "sections": {
    "1. Organization vision, mission, strategy, and key outcomes": {
      "1.1 Mission": "800-1200",
      "1.6 Strategic initiatives": "2500-3500"
    }
  }
}
```

### Adding Table Format Instructions

For sections requiring specific table structures:

```json
{
  "2.1 Revenue by Business Segment": "800-1200. Include a table with three columns: Business Unit | Lines of Business | Revenue (Last Full Fiscal Year in $B)."
}
```

### Enterprise-Specific Prompts

Modify `profile_builder.py` to load enterprise-specific context:

```python
# Add industry-specific guidance
if "Aerospace" in industry:
    prompt += "\nFocus on aircraft production, defense contracts, and regulatory compliance."
```

## Performance & Cost Optimization

### API Token Usage

Each enterprise profile uses approximately:
- **Tokens per subsection**: 1,000-3,000 (depending on word count)
- **Total subsections**: ~90
- **Estimated tokens per enterprise**: 90,000-270,000
- **GPT-4o cost**: ~$1.50-$4.50 per enterprise (varies by date)

### Optimization Strategies

1. **Reduce word counts** for testing:
   ```json
   {"default_word_count": "400-600"}
   ```

2. **Process subset** for validation:
   ```bash
   python3 batch_generate.py --limit 1
   ```

3. **Use rate limiting** to spread API calls:
   ```bash
   python3 batch_generate.py --workers 2 --rate-limit 15
   ```

4. **Monitor partial saves**:
   - Script saves `profile_detailed_partial.json` after each subsection
   - If interrupted, resume with `--force` or manually copy partial → detailed.json

## Troubleshooting

### JSON Parsing Errors

If API returns malformed JSON:
- Check `error_response_*.txt` in output directory
- Script automatically retries 3 times with compact mode
- Review OpenAI API status for service issues

### Memory Issues with Parallel Workers

If system runs out of memory:
```bash
# Reduce workers
python3 batch_generate.py --workers 1 --limit 10

# Or add delays
python3 batch_generate.py --workers 2 --rate-limit 30
```

### Word Document Formatting

To update TOC in Word:
1. Open the .docx file
2. Right-click Table of Contents
3. Select "Update Field" → "Update entire table"

### Missing CSV Exports

CSVs are only exported when:
- A section contains a key named exactly `"Table"`
- The value is a list of dictionaries with consistent keys
- Check section structure in JSON to ensure proper format

## Examples

### Example 1: Quick Test Run

```bash
# Test with one enterprise
python3 batch_generate.py --limit 1

# Check output
ls -lh batch_outputs/airbus/
cat batch_outputs/batch_summary.json
```

### Example 2: Production Batch

```bash
# Process all 25 enterprises with parallelization
python3 batch_generate.py \
  --workers 3 \
  --rate-limit 10 \
  --out-dir production_batch_$(date +%Y%m%d)

# Monitor progress
tail -f production_batch_*/batch.log
```

### Example 3: Resume Interrupted Batch

```bash
# First run (interrupted after 5 enterprises)
python3 batch_generate.py --limit 10

# Resume (skips first 5, processes remaining 5)
python3 batch_generate.py --limit 10
# Automatically detects existing outputs and skips them
```

### Example 4: Force Regenerate with Updates

```bash
# Update section_config.json with new word counts
# Then force regenerate first 3 enterprises
python3 batch_generate.py --limit 3 --force
```

## Dependencies

Ensure all dependencies are installed:

```bash
pip install openai>=1.40.0 python-dotenv>=1.2.1 python-docx pandas
```

## Environment Setup

Create `.env` file:
```
OPENAI_API_KEY=sk-your-api-key-here
```

## Support & Maintenance

### Updating Templates

To modify the structure:
1. Edit `operational_profile_template.json`
2. Update `section_config.json` with corresponding word counts
3. Test with `--limit 1` before batch processing

### Adding New Enterprises

Add rows to `Accounts.csv` with columns:
- `Enterprise` (required)
- `Industry`, `Sector`, `2024 Revenue`, `Number of Employees` (optional, for context)
- `Revenue Reporting Operating Unit 1-10` (optional, for table generation)

### Version Control

Recommended `.gitignore` entries:
```
batch_outputs/
outputs/
.env
*.pyc
__pycache__/
error_response_*.txt
_temp_builder_*.py
```

## Changelog

### v2.0 (Current)
- ✅ Parameterized `profile_builder.py` with `--enterprise` flag
- ✅ Parallel processing with worker pool
- ✅ Incremental resume capability
- ✅ Custom output directory support
- ✅ Structured JSON logging per enterprise
- ✅ Rate limiting for API quota management
- ✅ Table of Contents in Word documents
- ✅ CSV export of embedded tables

### v1.0 (Legacy)
- Basic batch processing
- Text substitution approach
- Sequential processing only

## License & Attribution

Generated profiles are for internal consulting use. Ensure compliance with:
- OpenAI usage policies
- Data privacy regulations for enterprise information
- Client confidentiality agreements
