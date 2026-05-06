#!/bin/bash
# Remaining experiments: GPT (3 batches) + Gemini-ER (7 batches)

export PYTHONPATH="/Users/doguyeke/Desktop/research/automated"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
SCRIPT="/Users/doguyeke/Desktop/research/automated/test_main.py"

source ~/.zshrc 2>/dev/null

echo "========================================"
echo " Remaining Experiments - $(date)"
echo "========================================"

# --- GPT (remaining 3 batches) ---
echo ""
echo "=== GPT MODEL (remaining) ==="

echo "[$(date +%H:%M)] GPT: fifth.png - white cup, pear"
$PYTHON $SCRIPT --task pick_up --model gpt --images fifth.png --objects "white cup" "pear" --iterations 10

echo "[$(date +%H:%M)] GPT: sixth.png - orange"
$PYTHON $SCRIPT --task pick_up --model gpt --images sixth.png --objects "orange" --iterations 10

echo "[$(date +%H:%M)] GPT: seventh.png - green plate, Coca-Cola bottle"
$PYTHON $SCRIPT --task pick_up --model gpt --images seventh.png --objects "green plate" "Coca-Cola bottle" --iterations 10

# --- GEMINI-ER (all 7 batches) ---
echo ""
echo "=== GEMINI-ER MODEL ==="

echo "[$(date +%H:%M)] Gemini-ER: first.png - cherries can, peaches can, orange juice box"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images first.png --objects "cherries can" "peaches can" "orange juice box" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: second.png - white mug, apple, Cheez-It box"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images second.png --objects "white mug" "apple" "Cheez-It box" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: third.png - banana, knife, cutting board"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images third.png --objects "banana" "knife" "cutting board" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: fourth.png - red plate"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images fourth.png --objects "red plate" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: fifth.png - white cup, pear"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images fifth.png --objects "white cup" "pear" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: sixth.png - orange"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images sixth.png --objects "orange" --iterations 10

echo "[$(date +%H:%M)] Gemini-ER: seventh.png - green plate, Coca-Cola bottle"
$PYTHON $SCRIPT --task pick_up --model gemini-er --images seventh.png --objects "green plate" "Coca-Cola bottle" --iterations 10

echo ""
echo "========================================"
echo " All Remaining Experiments Completed"
echo " $(date)"
echo "========================================"
