#!/bin/bash
# Run 8 scenarios (2 per task × 4 tasks) on final_dataset images for ONE model.
# Usage: ./scripts/run_final_dataset.sh <gemini|gpt|gemini-er-1.6>
set -e
cd "$(dirname "$0")/.."

MODEL="$1"
if [ -z "$MODEL" ]; then echo "Usage: $0 <model>"; exit 1; fi

export GOOGLE_CLOUD_PROJECT=dogu-robi
export GOOGLE_CLOUD_LOCATION=global
# Source zshrc-style key for ER preview models
[ -f ~/.zshrc ] && source ~/.zshrc 2>/dev/null
export GeminiER_KEY="${GeminiER_KEY:-}"

run() {
    local TASK="$1"; local IMG="$2"; local OBJ="$3"; local ATTR="$4"
    echo ""
    echo "================================================================"
    echo " [$MODEL] task=$TASK  img=$IMG  obj/query=$OBJ  attr=$ATTR"
    echo "================================================================"
    if [ -n "$ATTR" ]; then
        python test_main.py --task "$TASK" --model "$MODEL" \
            --image-dir final_dataset --images "$IMG" \
            --objects "$OBJ" --attribute "$ATTR" \
            --iterations 10
    else
        python test_main.py --task "$TASK" --model "$MODEL" \
            --image-dir final_dataset --images "$IMG" \
            --objects "$OBJ" \
            --iterations 10
    fi
}

# pick_up
run pick_up   "9_hope.jpg"      "orange Macaroni and Cheese box"  ""
run pick_up   "1_droid.png"     "small clear plastic bottle"      ""
# detection
run detection "8_hope.jpg"      "Raisins box"                     ""
run detection "2_robo2vlm.png"  "soda can"                        ""
# ambiguity
run ambiguity "5_hope.png"      "The Corny box"                   ""
run ambiguity "2_egothink.jpg"  "the red pillow"                  ""
# attribute
run attribute "1_hope.png"      "Oven"                            "opened"
run attribute "1_droid.png"     "microwave oven door"             "closed"

echo ""
echo "[$MODEL] Done."
