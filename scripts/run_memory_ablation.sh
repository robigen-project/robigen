#!/bin/bash
# Memory ablation: 8 scenarios × 5 iterations × 2 conditions.
# 2 per task (pick_up, detection, ambiguity, attribute), all from
# the hope dataset.
#
# Usage: ./scripts/run_memory_ablation.sh on   (results/<task>_gemini/)
#        ./scripts/run_memory_ablation.sh off  (results/<task>_gemini_nomem/)

set -e
cd "$(dirname "$0")/.."

if [ "$1" = "on" ]; then
    FLAG=""
    LABEL="WITH-MEM"
elif [ "$1" = "off" ]; then
    FLAG="--no-memory"
    LABEL="NO-MEM"
else
    echo "Usage: $0 [on|off]"
    exit 1
fi

export GOOGLE_CLOUD_PROJECT=dogu-robi
export GOOGLE_CLOUD_LOCATION=global

run_scenario() {
    local TASK="$1"
    local IMG="$2"
    local OBJ="$3"
    local ATTR="$4"
    echo ""
    echo "================================================================"
    echo " [$LABEL] task=$TASK  img=$IMG  obj/query=$OBJ  attr=$ATTR"
    echo "================================================================"
    if [ -n "$ATTR" ]; then
        python test_main.py --task "$TASK" --model gemini \
            --image-dir hope --images "$IMG" \
            --objects "$OBJ" --attribute "$ATTR" \
            --iterations 10 $FLAG
    else
        python test_main.py --task "$TASK" --model gemini \
            --image-dir hope --images "$IMG" \
            --objects "$OBJ" \
            --iterations 10 $FLAG
    fi
}

# 1-2. pick_up
run_scenario pick_up   "0000_rgb copy 2.jpg" "orange juice carton"     ""
run_scenario pick_up   "0000_rgb copy 3.jpg" "yellow mustard bottle"   ""
# 3-4. detection
run_scenario detection "0000_rgb copy 2.jpg" "Corn can"                ""
run_scenario detection "0000_rgb copy 3.jpg" "can"                     ""
# 5-6. ambiguity
run_scenario ambiguity "0000_rgb copy 3.jpg" "the can of tomato sauce" ""
run_scenario ambiguity "0000_rgb copy 4.jpg" "the box"                 ""
# 7-8. attribute
run_scenario attribute "0000_rgb copy 3.jpg" "Alphabet Soup can"       "Sealed"
run_scenario attribute "0000_rgb copy 4.jpg" "Alphabet Soup can"       "sealed"

echo ""
echo "[$LABEL] Done."
