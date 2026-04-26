#!/usr/bin/env bash
# Прогон прототипа на canonical-корпусе Accumulator + открыть дашборд.
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p reports

python3 storytelling_bot.py \
    --entity accumulator \
    --output reports/accumulator_demo.json \
    --export-html reports/accumulator_demo.html

echo
echo "✓ JSON:      reports/accumulator_demo.json"
echo "✓ Дашборд:   reports/accumulator_demo.html"
echo
case "$(uname -s)" in
  Darwin) open reports/accumulator_demo.html ;;
  Linux)  xdg-open reports/accumulator_demo.html 2>/dev/null || true ;;
esac
