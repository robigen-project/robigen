#!/bin/bash
# Run 4 hope pick_up scenarios for ONE model at K=10 multi-eval.
# Usage: ./scripts/run_3model_pickup.sh <gemini|gpt|gemini-er>
set -e
cd "$(dirname "$0")/.."

MODEL="$1"
if [ -z "$MODEL" ]; then echo "Usage: $0 <model>"; exit 1; fi

export GOOGLE_CLOUD_PROJECT=dogu-robi
export GOOGLE_CLOUD_LOCATION=global

run_pick() {
    local IMG="$1"; local OBJ="$2"
    echo ""
    echo "============================================================"
    echo " [$MODEL] $IMG / $OBJ"
    echo "============================================================"
    python test_main.py --task pick_up --model "$MODEL" \
        --image-dir hope --images "$IMG" \
        --objects "$OBJ" --iterations 10
}

run_pick "0000_rgb copy 2.jpg" "orange juice carton"
run_pick "0000_rgb copy 3.jpg" "yellow mustard bottle"
run_pick "0000_rgb copy 4.jpg" "orange Macaroni and Cheese box"
run_pick "0000_rgb copy 7.jpg" "Creamy Ranch Dressing bottle"

echo ""
echo "[$MODEL] Done."
