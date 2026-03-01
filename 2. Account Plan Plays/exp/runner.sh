#!/usr/bin/env bash
set -euo pipefail

# Create logs folder if missing
mkdir -p logs

echo "Loading environment variables..."
source setup_env_var.sh

echo "Running extract_use_case_from_ppt.py..."
python3 extract_use_case_from_ppt.py 2>&1 | tee logs/extract_use_case_from_ppt.log

echo "Running map_chessboard.py..."
python3 map_chessboard.py 2>&1 | tee logs/map_chessboard.log

echo "Running map_innovation_themes.py..."
python3 map_innovation_themes.py 2>&1 | tee logs/map_innovation_themes.log

echo "Pipeline completed successfully."
