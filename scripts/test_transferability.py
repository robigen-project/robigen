#!/usr/bin/env python3
"""
Test transferability of adversarial attacks across models.

For each successful attack against Model A, replay the same adversarial
image against Model B and check if it's also tricked.

Usage:
    python scripts/test_transferability.py --source-model gemini --target-model gpt
"""

import os
import sys
import json
import argparse
import glob

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.embodied_agent import EmbodiedAgentUnderTest
from agents.consensus_agent import ConsensusAgent
from config.tasks import get_prompt_for_task


def find_successful_attacks(source_model):
    """Find all successful adversarial images for a given source model."""
    results_dir = "results"
    attacks = []

    for task_model in os.listdir(results_dir):
        if not task_model.endswith(f"_{source_model}"):
            continue

        task_type = task_model.replace(f"_{source_model}", "").replace("_nomem", "")
        task_model_path = os.path.join(results_dir, task_model)

        for test_name in os.listdir(task_model_path):
            test_path = os.path.join(task_model_path, test_name)
            summary_file = os.path.join(test_path, "summary.json")

            if not os.path.exists(summary_file):
                continue

            with open(summary_file) as f:
                data = json.load(f)

            for iteration in data.get("tricked_iterations", []):
                iter_dir = os.path.join(test_path, f"iteration_{iteration}")
                # Find the adversarial image
                adv_images = glob.glob(os.path.join(iter_dir, "modified_retry_*.png"))
                if adv_images:
                    attacks.append({
                        "task_type": task_type,
                        "test_name": test_name,
                        "iteration": iteration,
                        "target_object": data.get("target", ""),
                        "attribute": data.get("attribute"),
                        "adversarial_image": adv_images[-1],  # Use last retry (usually best)
                    })

    return attacks


def test_attack_on_model(attack, target_model_type, evaluator):
    """Test a single adversarial image against a different model."""
    target_agent = EmbodiedAgentUnderTest(model_type=target_model_type)

    # Run the target model on the adversarial image
    output = target_agent.run_task(
        attack["adversarial_image"],
        attack["task_type"],
        attack["target_object"],
        attack.get("attribute")
    )

    # Get the prompt for evaluation
    prompt = get_prompt_for_task(
        attack["task_type"],
        attack["target_object"],
        attack.get("attribute")
    )

    # Evaluate
    is_correct, reasoning = evaluator.evaluate(
        attack["adversarial_image"],
        prompt,
        output,
        task_type=attack["task_type"],
        target_object=attack["target_object"],
        attribute=attack.get("attribute")
    )

    return {
        "tricked": not is_correct,
        "output": output,
        "reasoning": reasoning,
    }


def main():
    parser = argparse.ArgumentParser(description="Test attack transferability between models")
    parser.add_argument("--source-model", required=True, help="Model the attacks were generated against")
    parser.add_argument("--target-model", required=True, help="Model to test transferability on")
    parser.add_argument("--single-evaluator", action="store_true", help="Use single evaluator")
    parser.add_argument("--max-attacks", type=int, default=0, help="Max attacks to test (0=all)")
    args = parser.parse_args()

    print(f"Transferability Test: {args.source_model} -> {args.target_model}")
    print("=" * 60)

    # Find attacks
    attacks = find_successful_attacks(args.source_model)
    print(f"Found {len(attacks)} successful attacks against {args.source_model}")

    if not attacks:
        print("No attacks found. Run experiments first.")
        return

    if args.max_attacks > 0:
        attacks = attacks[:args.max_attacks]
        print(f"Testing first {len(attacks)} attacks")

    # Initialize evaluator
    if args.single_evaluator:
        from agents.evaluation_agent import EvaluationAgent
        evaluator = EvaluationAgent()
    else:
        evaluator = ConsensusAgent()

    # Test each attack
    transferred = 0
    total = 0
    results = []

    for i, attack in enumerate(attacks):
        print(f"\n--- Attack {i+1}/{len(attacks)} ---")
        print(f"Task: {attack['task_type']}, Target: {attack['target_object']}")
        print(f"Image: {attack['adversarial_image']}")

        try:
            result = test_attack_on_model(attack, args.target_model, evaluator)
            total += 1
            if result["tricked"]:
                transferred += 1
                print(f"TRANSFERRED - {args.target_model} also tricked!")
            else:
                print(f"NOT TRANSFERRED - {args.target_model} not tricked")

            results.append({
                **attack,
                "transferred": result["tricked"],
                "target_model": args.target_model,
            })
        except Exception as e:
            print(f"ERROR: {e}")

    # Summary
    rate = (transferred / total * 100) if total > 0 else 0
    print(f"\n{'=' * 60}")
    print(f"TRANSFERABILITY: {args.source_model} -> {args.target_model}")
    print(f"Transferred: {transferred}/{total} ({rate:.1f}%)")
    print(f"{'=' * 60}")

    # Save results
    output_path = f"results/transferability_{args.source_model}_to_{args.target_model}.json"
    with open(output_path, "w") as f:
        json.dump({
            "source_model": args.source_model,
            "target_model": args.target_model,
            "total_tested": total,
            "transferred": transferred,
            "transfer_rate": rate,
            "details": results,
        }, f, indent=2, default=str)
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
