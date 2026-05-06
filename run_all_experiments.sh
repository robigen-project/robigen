#!/bin/bash
# Run all pick_up experiments overnight
# 15 scenarios × 3 models × 10 iterations = 450 iterations

export PYTHONPATH="/Users/doguyeke/Desktop/research/automated"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
SCRIPT="/Users/doguyeke/Desktop/research/automated/test_main.py"

# Source environment for API keys
source ~/.zshrc 2>/dev/null

echo "========================================"
echo " Starting Full Experiment Run"
echo " $(date)"
echo "========================================"

# --- GEMINI ---
echo ""
echo "=== GEMINI MODEL ==="

echo "[$(date +%H:%M)] Gemini: first.png - peaches can, orange juice box"
$PYTHON $SCRIPT --task pick_up --model gemini --images first.png --objects "peaches can" "orange juice box" --iterations 10

echo "[$(date +%H:%M)] Gemini: second.png - apple, Cheez-It box"
$PYTHON $SCRIPT --task pick_up --model gemini --images second.png --objects "apple" "Cheez-It box" --iterations 10

echo "[$(date +%H:%M)] Gemini: third.png - cutting board"
$PYTHON $SCRIPT --task pick_up --model gemini --images third.png --objects "cutting board" --iterations 10

echo "[$(date +%H:%M)] Gemini: fourth.png - red plate"
$PYTHON $SCRIPT --task pick_up --model gemini --images fourth.png --objects "red plate" --iterations 10

echo "[$(date +%H:%M)] Gemini: fifth.png - white cup, pear"
$PYTHON $SCRIPT --task pick_up --model gemini --images fifth.png --objects "white cup" "pear" --iterations 10

echo "[$(date +%H:%M)] Gemini: sixth.png - orange"
$PYTHON $SCRIPT --task pick_up --model gemini --images sixth.png --objects "orange" --iterations 10

echo "[$(date +%H:%M)] Gemini: seventh.png - green plate, Coca-Cola bottle"
$PYTHON $SCRIPT --task pick_up --model gemini --images seventh.png --objects "green plate" "Coca-Cola bottle" --iterations 10

# --- GPT ---
echo ""
echo "=== GPT MODEL ==="

echo "[$(date +%H:%M)] GPT: first.png - cherries can, peaches can, orange juice box"
$PYTHON $SCRIPT --task pick_up --model gpt --images first.png --objects "cherries can" "peaches can" "orange juice box" --iterations 10

echo "[$(date +%H:%M)] GPT: second.png - white mug, apple, Cheez-It box"
$PYTHON $SCRIPT --task pick_up --model gpt --images second.png --objects "white mug" "apple" "Cheez-It box" --iterations 10

echo "[$(date +%H:%M)] GPT: third.png - banana, knife, cutting board"
$PYTHON $SCRIPT --task pick_up --model gpt --images third.png --objects "banana" "knife" "cutting board" --iterations 10

echo "[$(date +%H:%M)] GPT: fourth.png - red plate"
$PYTHON $SCRIPT --task pick_up --model gpt --images fourth.png --objects "red plate" --iterations 10

echo "[$(date +%H:%M)] GPT: fifth.png - white cup, pear"
$PYTHON $SCRIPT --task pick_up --model gpt --images fifth.png --objects "white cup" "pear" --iterations 10

echo "[$(date +%H:%M)] GPT: sixth.png - orange"
$PYTHON $SCRIPT --task pick_up --model gpt --images sixth.png --objects "orange" --iterations 10

echo "[$(date +%H:%M)] GPT: seventh.png - green plate, Coca-Cola bottle"
$PYTHON $SCRIPT --task pick_up --model gpt --images seventh.png --objects "green plate" "Coca-Cola bottle" --iterations 10

# --- GEMINI-ER ---
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
echo " All Experiments Completed"
echo " $(date)"
echo "========================================"
