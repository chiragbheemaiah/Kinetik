import csv
import json
import argparse
import logging
import time
from pathlib import Path
import subprocess
import sys
from typing import List, Dict, Any
from datetime import datetime

"""
Batch generation script for sequential processing of multiple enterprises.
Processes one enterprise at a time with detailed timing and progress reporting.
"""

# Paths
ROOT_DIR = Path(__file__).parent
ACCOUNTS_CSV = ROOT_DIR / "Accounts.csv"
BUILDER_SCRIPT = ROOT_DIR / "profile_builder.py"
SECTION_CONFIG = ROOT_DIR / "section_config.json"
OUTPUT_ROOT = ROOT_DIR / "batch_outputs"
WORD_SCRIPT = ROOT_DIR / "create_word_doc.py"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(OUTPUT_ROOT / "batch.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def read_accounts(csv_path: Path, limit: int | None = None) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline='') as f:
        content = f.read().splitlines()
    if not content:
        return []
    # Handle BOM in first header
    if content[0].startswith('\ufeff'):
        content[0] = content[0].lstrip('\ufeff')
    reader = csv.DictReader(content)
    for r in reader:
        # Skip empty lines (Enterprise blank)
        ent = (r.get("Enterprise") or r.get("\ufeffEnterprise") or "").strip()
        if not ent:
            continue
        rows.append(r)
        if limit and len(rows) >= limit:
            break
    return rows

def slugify(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")

def enterprise_already_processed(enterprise_slug: str, output_root: Path) -> bool:
    dest_dir = output_root / enterprise_slug
    json_path = dest_dir / "profile_detailed.json"
    return json_path.exists()

def run_builder(enterprise: str, output_dir: Path) -> Path:
    # Use parameterized profile_builder.py with --enterprise flag
    result = subprocess.run(
        [sys.executable, str(BUILDER_SCRIPT), "--enterprise", enterprise, "--output-dir", str(output_dir)],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.error(f"profile_builder failed for {enterprise}")
        logger.error(f"STDERR: {result.stderr}")
        raise RuntimeError(f"profile_builder failed for {enterprise}")
    output_json = output_dir / "profile_detailed.json"
    if not output_json.exists():
        raise FileNotFoundError(f"Expected profile_detailed.json not found for {enterprise}")
    return output_json

def generate_word(dest_dir: Path, enterprise_slug: str) -> Path:
    docx_path = dest_dir / f"{enterprise_slug}_operational_profile.docx"
    result = subprocess.run([
        sys.executable, str(WORD_SCRIPT), 
        "--input", str(dest_dir / "profile_detailed.json"), 
        "--output", str(docx_path), 
        "--export-csv-dir", str(dest_dir / "tables")
    ], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"create_word_doc.py failed for {enterprise_slug}")
        logger.error(f"STDERR: {result.stderr}")
        raise RuntimeError(f"create_word_doc.py failed")
    return docx_path

def save_log_json(dest_dir: Path, log_data: Dict[str, Any]) -> None:
    log_path = dest_dir / "process_log.json"
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

def process_account(row: Dict[str, str], output_root: Path, force: bool = False) -> Dict[str, Any]:
    start_time = time.time()
    enterprise = row.get("Enterprise") or "Unknown"
    enterprise_slug = slugify(enterprise)
    dest_dir = output_root / enterprise_slug
    
    log_data = {
        "enterprise": enterprise,
        "slug": enterprise_slug,
        "start_time": datetime.now().isoformat(),
        "status": "started"
    }
    
    # Check if already processed
    if not force and enterprise_already_processed(enterprise_slug, output_root):
        logger.info(f"Skipping {enterprise} - already processed (use --force to regenerate)")
        log_data["status"] = "skipped"
        log_data["reason"] = "already_exists"
        log_data["end_time"] = datetime.now().isoformat()
        log_data["duration_seconds"] = time.time() - start_time
        return log_data
    
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Run builder
        logger.info(f"Running profile_builder for {enterprise}...")
        json_path = run_builder(enterprise, dest_dir)
        log_data["json_path"] = str(json_path)
        
        # Generate Word doc
        logger.info(f"Generating Word document for {enterprise}...")
        word_path = generate_word(dest_dir, enterprise_slug)
        log_data["docx_path"] = str(word_path)
        
        log_data["status"] = "success"
        log_data["dir"] = str(dest_dir)
        
    except Exception as e:
        logger.error(f"Failed to process {enterprise}: {e}")
        log_data["status"] = "error"
        log_data["error"] = str(e)
    
    log_data["end_time"] = datetime.now().isoformat()
    log_data["duration_seconds"] = time.time() - start_time
    
    # Save individual log
    save_log_json(dest_dir, log_data)
    
    return log_data

def main():
    parser = argparse.ArgumentParser(description="Batch generate operational profiles for multiple enterprises (SEQUENTIAL MODE)")
    parser.add_argument("--csv", type=str, default=str(ACCOUNTS_CSV), help="Path to CSV file with enterprise accounts")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on number of accounts to process")
    parser.add_argument("--out-dir", type=str, default=str(OUTPUT_ROOT), help="Custom output directory for batch results")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if enterprise already processed")
    args = parser.parse_args()
    
    csv_path = Path(args.csv)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    
    output_root = Path(args.out_dir)
    output_root.mkdir(exist_ok=True, parents=True)
    
    # Ensure log directory
    (output_root / "batch.log").parent.mkdir(exist_ok=True)

    accounts = read_accounts(csv_path, limit=args.limit)
    if not accounts:
        logger.info("No accounts found to process.")
        return

    logger.info(f"\n{'='*70}")
    logger.info(f"BATCH PROCESSING - SEQUENTIAL MODE")
    logger.info(f"{'='*70}")
    logger.info(f"Total enterprises to process: {len(accounts)}")
    logger.info(f"Force regeneration: {args.force}")
    logger.info(f"Output directory: {output_root}")
    logger.info(f"{'='*70}\n")

    results = []
    
    # Sequential processing only (one enterprise at a time)
    for i, row in enumerate(accounts, 1):
        enterprise = row.get("Enterprise")
        logger.info(f"\n{'─'*70}")
        logger.info(f"[{i}/{len(accounts)}] PROCESSING: {enterprise}")
        logger.info(f"{'─'*70}")
        try:
            res = process_account(row, output_root, force=args.force)
            results.append(res)
            
            if res.get("status") == "success":
                duration = res.get("duration_seconds", 0)
                logger.info(f"✓ SUCCESS - Completed in {duration:.1f}s")
                logger.info(f"  Output: {res['dir']}")
                
                # Check if timing file exists and show summary
                timing_file = Path(res['dir']) / "generation_timing.json"
                if timing_file.exists():
                    with open(timing_file, 'r') as f:
                        timing = json.load(f)
                    logger.info(f"  Subsections: {timing.get('successful_subsections', 0)}/{timing.get('total_subsections', 0)} successful")
                    logger.info(f"  Total generation time: {timing.get('total_duration_seconds', 0):.1f}s")
                    
            elif res.get("status") == "skipped":
                logger.info(f"⊘ SKIPPED - Already exists (use --force to regenerate)")
        except Exception as e:
            logger.error(f"✗ FAILED - {e}")
            results.append({
                "enterprise": enterprise,
                "status": "error",
                "error": str(e)
            })

    # Summary JSON
    summary_path = output_root / "batch_summary.json"
    summary = {
        "batch_start": datetime.now().isoformat(),
        "total_accounts": len(accounts),
        "processed": len([r for r in results if r.get("status") == "success"]),
        "skipped": len([r for r in results if r.get("status") == "skipped"]),
        "failed": len([r for r in results if r.get("status") == "error"]),
        "results": results
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"BATCH PROCESSING COMPLETE")
    logger.info(f"{'='*70}")
    logger.info(f"Total enterprises: {summary['total_accounts']}")
    logger.info(f"✓ Successfully processed: {summary['processed']}")
    logger.info(f"⊘ Skipped (already exists): {summary['skipped']}")
    logger.info(f"✗ Failed: {summary['failed']}")
    logger.info(f"\nSummary saved to: {summary_path}")
    logger.info(f"{'='*70}\n")

if __name__ == "__main__":
    main()
