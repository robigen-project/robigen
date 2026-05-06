import os
import sys
import time
import json
import re
import argparse
import shutil
import logging

# Suppress HTTP request logging noise from httpx, urllib3, and openai
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from agents.embodied_agent import EmbodiedAgentUnderTest
from agents.evaluation_agent import EvaluationAgent
from agents.consensus_agent import ConsensusAgent
from agents.semantic_scene_creation_agent import SemanticSceneCreationAgent
from agents.scene_synthesis_agent import SceneSynthesisAgent
from agents.constraint_enforcement_agent import ConstraintEnforcementAgent
from config.tasks import get_task_config, get_prompt_for_task, VALID_TASK_TYPES
from config.models import VALID_MODEL_TYPES, get_model_config
from utils import metrics
from utils.logger import setup_logger
from utils.formatters import (
    format_target_output,
    format_action_output,
    format_action_summary,
    format_evaluator_output,
    strip_markdown
)


# Test counter file path
TEST_COUNTER_FILE = "results/.test_counter.json"


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}\n")


def sanitize_filename(name):
    return re.sub(r'[^\w\-_]', '_', name)[:30]


def get_next_test_number(results_dir: str) -> int:
    """Get the next test number for a results directory."""
    counter_file = os.path.join(results_dir, ".test_counter")
    if os.path.exists(counter_file):
        with open(counter_file, "r") as f:
            count = int(f.read().strip())
    else:
        count = 0

    # Increment and save
    count += 1
    os.makedirs(results_dir, exist_ok=True)
    with open(counter_file, "w") as f:
        f.write(str(count))

    return count


def list_tests(results_base: str = "results"):
    """List all test folders across all task/model combinations."""
    if not os.path.exists(results_base):
        print("No results directory found.")
        return []

    all_tests = []

    for task_model_dir in sorted(os.listdir(results_base)):
        task_model_path = os.path.join(results_base, task_model_dir)
        if not os.path.isdir(task_model_path):
            continue

        for test_folder in sorted(os.listdir(task_model_path)):
            test_path = os.path.join(task_model_path, test_folder)
            if os.path.isdir(test_path) and not test_folder.startswith('.'):
                all_tests.append({
                    "task_model": task_model_dir,
                    "folder": test_folder,
                    "path": test_path
                })

    return all_tests


def remove_tests(target: str, results_base: str = "results"):
    """
    Remove test folders.

    Args:
        target: 'all' to remove everything, or a specific test folder name
        results_base: Base results directory
    """
    if target.lower() == "all":
        if os.path.exists(results_base):
            confirm = input(f"Are you sure you want to delete ALL tests in {results_base}/? (yes/no): ")
            if confirm.lower() == "yes":
                shutil.rmtree(results_base)
                print(f"Removed all tests in {results_base}/")
            else:
                print("Cancelled.")
        else:
            print("No results directory found.")
        return

    # Find and remove specific test
    all_tests = list_tests(results_base)
    matches = [t for t in all_tests if target in t["folder"]]

    if not matches:
        print(f"No test folder matching '{target}' found.")
        print("\nAvailable tests:")
        for t in all_tests:
            print(f"  {t['task_model']}/{t['folder']}")
        return

    if len(matches) > 1:
        print(f"Multiple matches found for '{target}':")
        for i, t in enumerate(matches):
            print(f"  [{i}] {t['task_model']}/{t['folder']}")
        choice = input("Enter number to delete (or 'all' for all matches, 'cancel' to abort): ")

        if choice.lower() == "cancel":
            print("Cancelled.")
            return
        elif choice.lower() == "all":
            for t in matches:
                shutil.rmtree(t["path"])
                print(f"Removed: {t['path']}")
        else:
            try:
                idx = int(choice)
                if 0 <= idx < len(matches):
                    shutil.rmtree(matches[idx]["path"])
                    print(f"Removed: {matches[idx]['path']}")
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid selection.")
    else:
        shutil.rmtree(matches[0]["path"])
        print(f"Removed: {matches[0]['path']}")


def _log_borderline_case(results_dir: str, case_data: dict):
    """Append a borderline case to the borderline_cases.jsonl file for human review."""
    borderline_path = os.path.join(results_dir, "borderline_cases.jsonl")
    with open(borderline_path, "a") as f:
        f.write(json.dumps(case_data, default=str) + "\n")


def run_scenario(agents, image_filename, target_object, config, scenario_index, total_scenarios):
    """
    Runs a single scenario (image + object combination) for the specified task.
    """
    target_agent, evaluator_agent, action_agent, image_agent, constraint_agent = agents

    image_dir = config['image_dir']
    results_dir = config['results_dir']
    k = config['iterations']
    task_type = config['task_type']
    attribute = config.get('attribute')

    # Create Independent Results Directory with test number
    clean_target = sanitize_filename(target_object)
    clean_image = sanitize_filename(image_filename.rsplit('.', 1)[0])

    # Get next test number for this results directory
    test_num = get_next_test_number(results_dir)

    # New naming format: {object}_{image}_test_{number}
    test_folder_name = f"{clean_target}_{clean_image}_test_{test_num}"

    scenario_dir = os.path.join(results_dir, test_folder_name)
    if not os.path.exists(scenario_dir):
        os.makedirs(scenario_dir)

    original_image_path = os.path.join(image_dir, image_filename)

    action_agent.reset_memory()

    # Generate task-specific prompt
    base_prompt = get_prompt_for_task(task_type, target_object, attribute)

    # Init Summary for valid scenario
    summary_file_path = os.path.join(scenario_dir, "summary.txt")
    summary_data = {
        "test_name": test_folder_name,
        "test_number": test_num,
        "task_type": task_type,
        "model": config.get('model'),
        "image": image_filename,
        "target": target_object,
        "attribute": attribute,
        "total_iterations": k,
        "successful_tricks": 0,
        "tricked_iterations": [],
        "constraint_stats": {
            "total_renders": 0,
            "passed": 0,
            "rejected": 0,
            "iterations_fully_rejected": 0,
            "rejected_iterations_log": []
        }
    }

    def update_summary(iter_num, tricked, reason="", categories=None, significance=0):
        if tricked:
            summary_data["successful_tricks"] += 1
            summary_data["tricked_iterations"].append(iter_num)
            # Store detailed info for successful tricks
            if "tricked_details" not in summary_data:
                summary_data["tricked_details"] = []
            summary_data["tricked_details"].append({
                "iteration": iter_num,
                "categories": categories or [],
                "significance": significance,
                "reason": reason[:500] if reason else ""
            })

        with open(summary_file_path, "w") as f:
            f.write(f"Test Name: {test_folder_name}\n")
            f.write(f"Test Number: {test_num}\n")
            f.write(f"Task Type: {task_type}\n")
            f.write(f"Model: {config.get('model')}\n")
            f.write(f"Image: {image_filename}\n")
            f.write(f"Target: {target_object}\n")
            if attribute:
                f.write(f"Attribute: {attribute}\n")
            f.write(f"Total Iterations: {k}\n")
            f.write(f"Successful Tricks: {summary_data['successful_tricks']}\n")
            f.write(f"Success Rate: {(summary_data['successful_tricks']/k)*100:.1f}%\n")
            f.write(f"\nTricked Iterations: {summary_data['tricked_iterations']}\n")
            cs = summary_data.get("constraint_stats", {})
            f.write(f"\nConstraint Enforcement (C1-C4):\n")
            f.write(f"  Total Renders: {cs.get('total_renders', 0)}\n")
            f.write(f"  Passed: {cs.get('passed', 0)}\n")
            f.write(f"  Rejected: {cs.get('rejected', 0)}\n")
            f.write(f"  Iterations Fully Rejected: {cs.get('iterations_fully_rejected', 0)}\n")
            if tricked:
                f.write(f"\nLatest Success Reason (Iter {iter_num}): {reason}\n")

        # Also save as JSON
        json_path = os.path.join(scenario_dir, "summary.json")
        with open(json_path, "w") as f:
            json.dump(summary_data, f, indent=2)

    update_summary(0, False)

    print_header(f"Running Test {scenario_index}/{total_scenarios}")
    print(f"Test Folder: {test_folder_name}")
    print(f"Task: {task_type}")
    print(f"Model: {config.get('model')}")
    print(f"Target: {target_object}")
    if attribute:
        print(f"Attribute: {attribute}")
    print(f"Image: {image_filename}")
    print(f"Prompt: {base_prompt}")
    print(f"Saving to: {scenario_dir}")

    for i in range(k):
        print(f"\n--- Iteration {i+1}/{k} ---")

        iter_dir = os.path.join(scenario_dir, f"iteration_{i+1}")
        if not os.path.exists(iter_dir):
            os.makedirs(iter_dir)

        log_file_path = os.path.join(iter_dir, "log.txt")

        def log_msg(msg):
            with open(log_file_path, "a") as f:
                f.write(msg + "\n")

        log_msg(f"Iteration {i+1}/{k}")
        log_msg(f"Task Type: {task_type}")
        log_msg(f"Model: {config.get('model')}")
        log_msg(f"Original Image: {original_image_path}")
        log_msg(f"Prompt: {base_prompt}")

        robot_tricked = False
        current_image_path = original_image_path

        metrics.start_iteration(iter_dir)

        # 1. Target Agent (Baseline)
        print(f"    [1] Target Agent (Baseline)...")
        with metrics.step("target_baseline"):
            target_output = target_agent.run_task(current_image_path, task_type, target_object, attribute)

        # Console output (brief) - different format based on task
        if task_type in ("pick_up", "grasp"):
            location = target_output.get('location', 'N/A')
            print(f"        Location: {location}")
        elif task_type == "conditional_grasp":
            action = target_output.get('action', 'N/A')
            print(f"        Action: {action}")
        else:
            key_output = target_output.get('count', target_output.get('answer', target_output.get('is_unique', 'N/A')))
            print(f"        Output: {key_output}")

        # Log output (formatted, no JSON)
        log_msg(f"\n[1] TARGET AGENT (Baseline)")
        log_msg(format_target_output(task_type, target_output))

        # 2. Evaluator Agent (Baseline)
        print(f"    [2] Evaluator Agent (Baseline)...")
        with metrics.step("evaluator_baseline"):
            is_correct, reason = evaluator_agent.evaluate(
                current_image_path,
                base_prompt,
                target_output,
                task_type=task_type,
                target_object=target_object,
                attribute=attribute
            )

        # Get consensus details if using consensus evaluator
        log_msg(f"\n[2] EVALUATOR (Baseline)")
        baseline_failed_judges = []
        if hasattr(evaluator_agent, 'get_last_consensus_details'):
            consensus = evaluator_agent.get_last_consensus_details()
            if consensus:
                log_msg(format_evaluator_output(consensus, for_log=True))
                # Detect any judge that errored after retries
                baseline_failed_judges = [
                    r['judge_id'] for r in consensus.get('judge_details', [])
                    if r.get('error')
                ]
            else:
                log_msg(f"    Verdict: {'CORRECT' if is_correct else 'INCORRECT'}")
                log_msg(f"    Reason: {strip_markdown(reason)}")
        else:
            log_msg(f"    Verdict: {'CORRECT' if is_correct else 'INCORRECT'}")
            log_msg(f"    Reason: {strip_markdown(reason)}")

        # Skip iteration if any baseline judge failed after all retries —
        # we want every recorded verdict backed by full 6-judge consensus.
        if baseline_failed_judges:
            print(f"        SKIPPED: baseline judges failed after retries: {baseline_failed_judges}")
            log_msg(f"\n--- RESULT: SKIPPED - baseline judges failed: {baseline_failed_judges} ---")
            update_summary(i+1, False)
            metrics.end_iteration()
            continue

        if not is_correct:
            print("        FAILED on original image. Skipping iteration.")
            log_msg("FAILED ON ORIGINAL IMAGE. Stopping iteration.")
            update_summary(i+1, False)
            metrics.end_iteration()
            continue

        # 3. Semantic Scene Creation Agent — propose ONE edit
        print(f"    [3] Semantic Scene Creation Agent...")
        with metrics.step("action"):
            action_json = action_agent.propose_edit(
                current_image_path,
                target_object,
                target_output,
                reason,
                task_type=task_type,
                attribute=attribute
            )
        if isinstance(action_json, list) and len(action_json) > 0:
            action_json = action_json[0]
        last_action_json = action_json

        op = action_json.get('op', action_json.get('operation', 'unknown'))
        obj = action_json.get('object', 'object')
        print(f"        Strategy: {op} on {obj}")
        log_msg(f"\n[3] SEMANTIC SCENE CREATION AGENT")
        log_msg(format_action_output(action_json))

        # 4. Scene Synthesis + Constraint Enforcement Loop (M=5 renders)
        M = 5
        modified_image_path = None
        constraint_log = []

        if "error" in action_json:
            print("        Action Agent failed.")
            log_msg(f"Action Agent Error: {action_json}")
        else:
            for j in range(M):
                print(f"        [4] Scene Synthesis Render {j+1}/{M}...")
                temp_output_path = os.path.join(iter_dir, f"render_{j+1}.png")
                with metrics.step("image"):
                    candidate_image = image_agent.edit_image(current_image_path, action_json, output_path=temp_output_path)

                if not candidate_image:
                    print(f"        Render {j+1} FAILED to generate.")
                    log_msg(f"\n[4] SCENE SYNTHESIS (Render {j+1}/{M}) - FAILED to generate image")
                    constraint_log.append({"render": j + 1, "render_failed": True})
                    summary_data["constraint_stats"]["total_renders"] += 1
                    summary_data["constraint_stats"]["rejected"] += 1
                    continue

                # Constraint Enforcement DISABLED — auto-accept every render
                # so we can isolate the effect of the realism agent. Re-enable
                # by restoring the constraint_agent.verify(...) call here.
                print(f"        [4b] Constraint Enforcement DISABLED — auto-accept")
                passes, c_reason = True, "constraint enforcer disabled (--no-realism mode)"

                summary_data["constraint_stats"]["total_renders"] += 1
                if passes:
                    summary_data["constraint_stats"]["passed"] += 1
                else:
                    summary_data["constraint_stats"]["rejected"] += 1

                # Rename render BEFORE logging so log shows tagged filename
                tag = "ACCEPTED" if passes else "REJECTED"
                tagged_path = os.path.join(iter_dir, f"render_{j+1}_{tag}.png")
                try:
                    os.rename(candidate_image, tagged_path)
                    candidate_image = tagged_path
                except Exception:
                    pass

                verdict = "PASS" if passes else "FAIL"
                print(f"        Constraint Verdict: {verdict}  (saved as {os.path.basename(candidate_image)})")
                log_msg(f"\n[4] SCENE SYNTHESIS (Render {j+1}/{M})")
                log_msg(f"    Image File: {os.path.basename(candidate_image)}")
                log_msg(f"    Constraint Verdict: {verdict}")
                log_msg(f"    Reason: {c_reason}")

                constraint_log.append({
                    "render": j + 1,
                    "image": os.path.basename(candidate_image),
                    "passes": passes,
                    "reason": c_reason
                })

                if passes:
                    modified_image_path = candidate_image
                    break

            if not modified_image_path:
                print(f"    All {M} renders rejected by Constraint Enforcement Agent.")
                log_msg(f"\n--- RESULT: REJECTED — all {M} renders failed C1-C4 verification ---")
                rejection_summary = "; ".join(
                    f"render {c['render']}: {c.get('reason', 'render failed')}"
                    for c in constraint_log
                )
                action_agent.register_rejection(action_json, rejection_summary)
                summary_data["constraint_stats"]["iterations_fully_rejected"] += 1
                summary_data["constraint_stats"]["rejected_iterations_log"].append({
                    "iteration": i + 1,
                    "edit": action_json,
                    "constraint_log": constraint_log
                })

        # Always write per-iteration constraint log JSON for human inspection
        if constraint_log:
            with open(os.path.join(iter_dir, "constraint_log.json"), "w") as f:
                json.dump({
                    "iteration": i + 1,
                    "edit": action_json,
                    "max_renders": M,
                    "accepted_image": os.path.basename(modified_image_path) if modified_image_path else None,
                    "renders": constraint_log,
                }, f, indent=2)

        if modified_image_path:
            # 5. Target Agent (Adversarial)
            print(f"    [5] Target Agent (Adversarial)...")
            with metrics.step("target_adversarial"):
                adv_target_output = target_agent.run_task(modified_image_path, task_type, target_object, attribute)

            # Console output (brief) - different format based on task
            if task_type == "pick_up":
                adv_location = adv_target_output.get('location', 'N/A')
                print(f"        Location: {adv_location}")
            else:
                adv_key_output = adv_target_output.get('count', adv_target_output.get('answer', adv_target_output.get('is_unique', 'N/A')))
                print(f"        Output: {adv_key_output}")

            # Log output (formatted)
            log_msg(f"\n[5] TARGET AGENT (Adversarial)")
            log_msg(format_target_output(task_type, adv_target_output))

            # If the adversarial target call errored (e.g., 429 rate limit),
            # skip the iteration entirely — an API failure is NOT a trick.
            if adv_target_output.get("error"):
                err_msg = adv_target_output.get("error", "unknown error")
                print(f"\n    [!] Adversarial target call failed: {err_msg[:120]}")
                print(f"        Skipping iteration (API failure, not an adversarial success).")
                log_msg(f"\n--- RESULT: SKIPPED - adversarial target API error: {err_msg} ---")
                update_summary(i+1, False)
                if last_action_json:
                    action_agent.register_result(last_action_json, False, f"API error: {err_msg}")
                metrics.end_iteration()
                # Honor the same partial-cleanup rule as failed tricks.
                keep = {"metrics.json", "constraint_log.json"}
                for fname in os.listdir(iter_dir):
                    full = os.path.join(iter_dir, fname)
                    if fname in keep or (fname.startswith("render_") and fname.endswith(".png")):
                        continue
                    if os.path.isfile(full):
                        os.remove(full)
                    elif os.path.isdir(full):
                        shutil.rmtree(full, ignore_errors=True)
                print("    Waiting 10s...")
                time.sleep(10)
                continue

            # 6. Evaluator Agent (Adversarial)
            print(f"    [6] Evaluator (Adversarial)...")
            with metrics.step("evaluator_adversarial"):
                adv_is_correct, adv_reason = evaluator_agent.evaluate(
                    modified_image_path,
                    base_prompt,
                    adv_target_output,
                    task_type=task_type,
                    target_object=target_object,
                    attribute=attribute
                )

            # Log output (formatted)
            log_msg(f"\n[6] EVALUATOR (Adversarial)")
            adv_failed_judges = []
            if hasattr(evaluator_agent, 'get_last_consensus_details'):
                consensus = evaluator_agent.get_last_consensus_details()
                if consensus:
                    log_msg(format_evaluator_output(consensus, for_log=True))
                    adv_failed_judges = [
                        r['judge_id'] for r in consensus.get('judge_details', [])
                        if r.get('error')
                    ]
                else:
                    log_msg(f"    Verdict: {'CORRECT' if adv_is_correct else 'INCORRECT'}")
                    log_msg(f"    Reason: {strip_markdown(adv_reason)}")
            else:
                log_msg(f"    Verdict: {'CORRECT' if adv_is_correct else 'INCORRECT'}")
                log_msg(f"    Reason: {strip_markdown(adv_reason)}")

            # Skip iteration if any adversarial judge failed after retries —
            # only count tricks backed by full 6-judge consensus.
            if adv_failed_judges:
                print(f"        SKIPPED: adversarial judges failed after retries: {adv_failed_judges}")
                log_msg(f"\n--- RESULT: SKIPPED - adversarial judges failed: {adv_failed_judges} ---")
                update_summary(i+1, False)
                if last_action_json:
                    action_agent.register_result(last_action_json, False, f"judges failed: {adv_failed_judges}")
                metrics.end_iteration()
                # Cleanup like other failed iterations.
                keep = {"metrics.json", "constraint_log.json"}
                for fname in os.listdir(iter_dir):
                    full = os.path.join(iter_dir, fname)
                    if fname in keep or (fname.startswith("render_") and fname.endswith(".png")):
                        continue
                    if os.path.isfile(full):
                        os.remove(full)
                    elif os.path.isdir(full):
                        shutil.rmtree(full, ignore_errors=True)
                print("    Waiting 10s...")
                time.sleep(10)
                continue

            # MEMORY UPDATE: Was the robot tricked?
            robot_tricked = not adv_is_correct
            if last_action_json:
                action_agent.register_result(last_action_json, robot_tricked, adv_reason)

            # Log borderline cases for human review
            if hasattr(evaluator_agent, 'get_last_consensus_details'):
                adv_consensus = evaluator_agent.get_last_consensus_details()
                if adv_consensus and adv_consensus.get("needs_human_review"):
                    _log_borderline_case(config["results_dir"], {
                        "iteration": i + 1,
                        "image": modified_image_path,
                        "prompt": base_prompt,
                        "target_output": adv_target_output,
                        "vote_breakdown": adv_consensus.get("vote_breakdown"),
                        "judge_details": adv_consensus.get("judge_details"),
                    })

            if robot_tricked:
                print(f"\n    >>> SUCCESS - Robot Tricked! <<<")
                log_msg("\n--- RESULT: SUCCESS - ROBOT TRICKED ---")

                # Save the original (seed) image next to the adversarial render
                # so each tricked iteration is self-contained for inspection.
                try:
                    orig_ext = os.path.splitext(original_image_path)[1] or ".png"
                    shutil.copy(
                        original_image_path,
                        os.path.join(iter_dir, f"original{orig_ext}"),
                    )
                except Exception as e:
                    log_msg(f"    (warning: could not copy original image: {e})")

                # Categorize the attack
                from utils.categorizer import categorize_attack, get_category_names
                categories = categorize_attack(last_action_json) if last_action_json else ["uncategorized"]
                category_names = get_category_names(categories)
                print(f"    Categories: {', '.join(category_names)}")
                log_msg(f"    Attack Categories: {categories}")

                # Get significance from consensus
                adv_significance = 0
                if hasattr(evaluator_agent, 'get_last_consensus_details'):
                    adv_consensus = evaluator_agent.get_last_consensus_details()
                    if adv_consensus:
                        adv_significance = adv_consensus.get("average_significance", 0)

                update_summary(i+1, True, adv_reason, categories=categories, significance=adv_significance)
            else:
                print(f"\n    Robot NOT tricked.")
                log_msg("\n--- RESULT: FAILURE - ROBOT NOT TRICKED ---")
                update_summary(i+1, False)
        else:
            print("    Failed to generate valid image.")
            log_msg("\n--- RESULT: FAILED - Could not generate adversarial image ---")
            update_summary(i+1, False)
            if last_action_json:
                action_agent.register_result(last_action_json, False, "Image Generation Failed")

        metrics.end_iteration()

        # Only persist heavy iteration artifacts (log.txt, large eval JSONs)
        # when the victim was actually tricked. Always keep the render PNGs,
        # constraint_log.json, and metrics.json so the realism-agent dataset
        # grows with every iteration, regardless of trick outcome.
        if not robot_tricked:
            keep = {"metrics.json", "constraint_log.json"}
            for fname in os.listdir(iter_dir):
                full = os.path.join(iter_dir, fname)
                if fname in keep:
                    continue
                if fname.startswith("render_") and fname.endswith(".png"):
                    continue
                if os.path.isfile(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)

        print("    Waiting 10s...")
        time.sleep(10)

    return summary_data


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Multi-Agent VLM Adversarial Testing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run tests (uses consensus evaluator by default - 6 judges voting)
  python test_main.py --task pick_up --images first.png --objects "red mug" --iterations 5
  python test_main.py --task detection --model gpt --images first.png --objects "mug" --iterations 5
  python test_main.py --task attribute --attribute opened --images first.png --objects "can" --iterations 5

  # Use single evaluator instead of consensus (faster but potentially biased)
  python test_main.py --task pick_up --images first.png --objects "mug" --single-evaluator

  # List all tests
  python test_main.py --list

  # Remove specific test (by folder name or partial match)
  python test_main.py --remove cherries_can_first_test_1
  python test_main.py --remove test_3

  # Remove all tests
  python test_main.py --remove all

Evaluator Modes:
  - Consensus (default): 6 judges vote in parallel (Gemini x2, Llama x2, GPT x2)
    Requires: GOOGLE_API_KEY, GROQ_API_KEY, OPENAI_API_KEY
  - Single (--single-evaluator): Single Gemini judge (faster, may have bias)
    Requires: GOOGLE_API_KEY only

Test folders are named: {object}_{image}_test_{number}
Results are saved to: results/{task}_{model}/
        """
    )

    # Management commands (mutually exclusive with run mode)
    mgmt_group = parser.add_argument_group('Test Management')
    mgmt_group.add_argument(
        '--list',
        action='store_true',
        help="List all test folders"
    )
    mgmt_group.add_argument(
        '--remove',
        type=str,
        metavar='TARGET',
        help="Remove test folder(s). Use 'all' to remove everything, or specify folder name/partial match"
    )

    # Run mode arguments
    run_group = parser.add_argument_group('Run Tests')
    run_group.add_argument(
        '--task',
        type=str,
        choices=VALID_TASK_TYPES,
        help=f"Task type to run. Options: {', '.join(VALID_TASK_TYPES)}"
    )

    run_group.add_argument(
        '--model',
        type=str,
        default='gemini',
        choices=VALID_MODEL_TYPES,
        help=f"Target model to test. Options: {', '.join(VALID_MODEL_TYPES)} (default: gemini)"
    )

    run_group.add_argument(
        '--image-dir',
        type=str,
        default='hope',
        dest='image_dir',
        help="Directory containing test images (default: hope). Can also use dataset names: droid, egothink, hope, robo2vlm, robovqa"
    )

    run_group.add_argument(
        '--images',
        type=str,
        nargs='+',
        help="List of image filenames from the image directory"
    )

    run_group.add_argument(
        '--objects',
        type=str,
        nargs='+',
        help="List of target objects to test"
    )

    run_group.add_argument(
        '--attribute',
        type=str,
        default=None,
        help="Attribute to test (required for 'attribute' task). E.g., 'opened', 'empty', 'damaged'"
    )

    run_group.add_argument(
        '--iterations',
        type=int,
        default=15,
        help="Number of iterations per scenario (default: 15)"
    )

    run_group.add_argument(
        '--single-evaluator',
        action='store_true',
        dest='single_evaluator',
        help="Use single Gemini evaluator instead of consensus (faster but potentially biased)"
    )

    run_group.add_argument(
        '--no-memory',
        action='store_true',
        dest='no_memory',
        help="Disable action agent memory (ablation study: no history between iterations)"
    )

    run_group.add_argument(
        '--random-action',
        action='store_true',
        dest='random_action',
        help="Use a non-LLM Random Object Insertion agent (baseline ablation)."
    )

    args = parser.parse_args()

    # Handle management commands
    if args.list or args.remove:
        return args

    # Validation for run mode
    if not args.task:
        parser.error("--task is required when running tests")
    if not args.images:
        parser.error("--images is required when running tests")
    if not args.objects:
        parser.error("--objects is required when running tests")
    if args.task in ('attribute', 'conditional_grasp') and not args.attribute:
        parser.error(f"--attribute is required when using --task {args.task}")

    return args


def main():
    args = parse_args()

    # Handle management commands
    if args.list:
        print_header("All Test Folders")
        tests = list_tests()
        if not tests:
            print("No tests found.")
        else:
            current_task_model = None
            for t in tests:
                if t["task_model"] != current_task_model:
                    current_task_model = t["task_model"]
                    print(f"\n{current_task_model}/")
                print(f"  └── {t['folder']}")
            print(f"\nTotal: {len(tests)} test folders")
        return

    if args.remove:
        remove_tests(args.remove)
        return

    # Run mode
    logger = setup_logger()
    clear_screen()
    print_header("Long-Tail Scenarios - Multi-Task Adversarial Testing")

    print(f"Task: {args.task}")
    print(f"Model: {args.model}")
    print(f"Images: {args.images}")
    print(f"Objects: {args.objects}")
    if args.attribute:
        print(f"Attribute: {args.attribute}")
    print(f"Iterations: {args.iterations}")
    evaluator_mode = "single" if args.single_evaluator else "consensus"
    print(f"Evaluator: {evaluator_mode}")
    memory_mode = "disabled" if args.no_memory else "enabled"
    print(f"Action Memory: {memory_mode}")

    print("\nInitializing Agents...")
    try:
        # Initialize Embodied Agent Under Test with selected model
        target_agent = EmbodiedAgentUnderTest(model_type=args.model)

        # Initialize Evaluator (consensus by default, single if --single-evaluator)
        if args.single_evaluator:
            print("  Using single Gemini evaluator")
            evaluator_agent = EvaluationAgent()
        else:
            print("  Using consensus agent (6 judges)")
            evaluator_agent = ConsensusAgent()

        if args.random_action:
            from agents.random_action_agent import RandomActionAgent
            action_agent = RandomActionAgent(enable_memory=not args.no_memory)
            print("  Using RandomActionAgent (baseline ablation — no LLM action proposer)")
        else:
            action_agent = SemanticSceneCreationAgent(enable_memory=not args.no_memory)
        image_agent = SceneSynthesisAgent()
        constraint_agent = ConstraintEnforcementAgent()
        print("  ConstraintEnforcementAgent initialized (C1-C4)")
        agents = (target_agent, evaluator_agent, action_agent, image_agent, constraint_agent)
        print("All agents initialized successfully.\n")
    except Exception as e:
        print(f"Error initializing agents: {e}")
        return

    # Resolve image directory (support dataset names or raw paths)
    from config.datasets import resolve_dataset_path
    image_dir = resolve_dataset_path(args.image_dir)

    # Validate images exist
    missing_images = []
    for img in args.images:
        if not os.path.exists(os.path.join(image_dir, img)):
            missing_images.append(img)

    if missing_images:
        print(f"ERROR: The following images were not found in {image_dir}/:")
        for img in missing_images:
            print(f"  - {img}")
        print("\nAvailable images:")
        for img in sorted(os.listdir(image_dir)):
            if img.lower().endswith(('.png', '.jpg', '.jpeg')):
                print(f"  - {img}")
        return

    # Create results directory: results/{task}_{model}/ or results/{task}_{model}_nomem/
    suffix_parts = []
    if args.random_action: suffix_parts.append("randact")
    if args.no_memory:     suffix_parts.append("nomem")
    if args.iterations == 1 and not args.random_action and not args.no_memory:
        suffix_parts.append("oneshot")
    dir_suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""
    results_dir = os.path.join("results", f"{args.task}_{args.model}{dir_suffix}")
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # Build scenario queue: all combinations of images and objects
    scenario_queue = []
    for img in args.images:
        for obj in args.objects:
            scenario_queue.append((img, obj))

    # Pack config
    config = {
        "image_dir": image_dir,
        "results_dir": results_dir,
        "iterations": args.iterations,
        "task_type": args.task,
        "attribute": args.attribute,
        "model": args.model
    }

    # Main Execution Loop
    print_header(f"Starting Test Queue: {len(scenario_queue)} Scenarios")
    print(f"Results will be saved to: {results_dir}/")

    master_stats = {
        "task_type": args.task,
        "model": args.model,
        "total_scenarios": len(scenario_queue),
        "completed": 0,
        "total_tricks": 0,
        "constraint_stats": {
            "total_renders": 0,
            "passed": 0,
            "rejected": 0,
            "iterations_fully_rejected": 0
        }
    }

    for i, (img, target) in enumerate(scenario_queue):
        result = run_scenario(agents, img, target, config, i+1, len(scenario_queue))

        master_stats["completed"] += 1
        master_stats["total_tricks"] += result["successful_tricks"]
        cs = result.get("constraint_stats", {})
        master_stats["constraint_stats"]["total_renders"] += cs.get("total_renders", 0)
        master_stats["constraint_stats"]["passed"] += cs.get("passed", 0)
        master_stats["constraint_stats"]["rejected"] += cs.get("rejected", 0)
        master_stats["constraint_stats"]["iterations_fully_rejected"] += cs.get("iterations_fully_rejected", 0)

    # Save master summary
    master_summary_path = os.path.join(results_dir, f"master_summary_{int(time.time())}.json")
    with open(master_summary_path, "w") as f:
        json.dump(master_stats, f, indent=2)

    print_header("All Tests Completed")
    print(f"Task: {args.task}")
    print(f"Model: {args.model}")
    print(f"Total Scenarios: {master_stats['total_scenarios']}")
    print(f"Total Successful Tricks: {master_stats['total_tricks']}")
    cs = master_stats["constraint_stats"]
    print(f"Constraint Enforcement (C1-C4):")
    print(f"  Total Renders: {cs['total_renders']}")
    print(f"  Passed: {cs['passed']}")
    print(f"  Rejected: {cs['rejected']}")
    print(f"  Iterations Fully Rejected: {cs['iterations_fully_rejected']}")
    print(f"Master Summary: {master_summary_path}")


if __name__ == "__main__":
    main()
