"""
Output formatting utilities for clean, readable logs.

Converts JSON data structures to human-readable text without
curly braces, quotes, colons, etc.
"""

import re


def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.
    Strips **bold**, *italic*, etc.
    """
    if not text:
        return text
    # Remove **bold**
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove *italic*
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove __underline__
    text = re.sub(r'__([^_]+)__', r'\1', text)
    # Remove _italic_
    text = re.sub(r'_([^_]+)_', r'\1', text)
    return text


def format_target_output(task_type: str, output: dict) -> str:
    """
    Format target agent output for logging.
    Returns clean text without JSON syntax.
    """
    lines = []

    if task_type in ("pick_up", "grasp"):
        location = strip_markdown(output.get('location', 'N/A'))
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Location: {location}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "conditional_grasp":
        action = output.get('action', 'N/A')
        location = strip_markdown(output.get('location', 'N/A'))
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Action: {action}")
        if location and location != 'None':
            lines.append(f"    Location: {location}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "collect_all":
        count = output.get('count', 'N/A')
        locations = output.get('locations', [])
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Count: {count}")
        if locations:
            for i, loc in enumerate(locations, 1):
                lines.append(f"    Location {i}: {strip_markdown(str(loc))}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "detection":
        count = output.get('count', 'N/A')
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Count: {count}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "ambiguity":
        is_unique = output.get('is_unique', 'N/A')
        candidates = output.get('candidates', [])
        clarification = output.get('clarification_question', 'N/A')
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Is Unique: {is_unique}")
        if candidates:
            lines.append(f"    Candidates: {', '.join(str(c) for c in candidates)}")
        if clarification:
            lines.append(f"    Clarification: {clarification}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "attribute":
        answer = output.get('answer', 'N/A')
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Answer: {answer}")
        lines.append(f"    Reason: {reason}")

    elif task_type == "multi_step":
        plan = output.get('action_plan', [])
        reason = strip_markdown(output.get('reason', 'N/A'))
        lines.append(f"    Action Plan ({len(plan)} steps):")
        for i, step in enumerate(plan, 1):
            lines.append(f"      {i}. {step}")
        lines.append(f"    Reason: {reason}")

    else:
        # Fallback for unknown task types
        for key, value in output.items():
            if key not in ['error', 'raw_response']:
                lines.append(f"    {key.replace('_', ' ').title()}: {value}")

    # Handle errors
    if 'error' in output:
        lines.append(f"    Error: {output['error']}")

    return '\n'.join(lines)


def format_action_output(action_json: dict) -> str:
    """
    Format action agent output for logging.
    Only includes: operation, object, location description, falsification logic.
    """
    lines = []

    # Operation
    op = action_json.get('op', action_json.get('operation', 'N/A'))
    lines.append(f"    Operation: {op}")

    # Object
    obj = action_json.get('object', 'N/A')
    lines.append(f"    Object: {obj}")

    # Location description
    loc = action_json.get('location_description', '')
    if loc:
        # Truncate if very long but keep it readable
        loc = strip_markdown(loc)
        if len(loc) > 300:
            loc = loc[:300] + "..."
        lines.append(f"    Location: {loc}")

    # Falsification logic (from properties)
    properties = action_json.get('properties', {})
    if isinstance(properties, dict):
        falsification = properties.get('falsification_logic', '')
        if falsification:
            falsification = strip_markdown(falsification)
            if len(falsification) > 300:
                falsification = falsification[:300] + "..."
            lines.append(f"    Falsification Logic: {falsification}")

    return '\n'.join(lines)


def format_action_summary(action_json: dict) -> str:
    """
    Format a short one-line summary of action for console output.
    """
    op = action_json.get('op', action_json.get('operation', 'unknown'))
    obj = action_json.get('object', 'object')
    loc = action_json.get('location_description', '')

    # Create brief description
    if loc:
        # Take first sentence or first 80 chars
        brief = loc.split('.')[0]
        if len(brief) > 80:
            brief = brief[:80] + "..."
    else:
        brief = f"Modifying {obj}"

    return f"    Strategy: {op}\n    Description: {brief}"


def format_vote_breakdown(vote_data: dict, judge_details: list) -> str:
    """
    Format vote breakdown with model names.
    Example: 4 INCORRECT [Llama-1, Llama-2, Gemini-2, GPT-1] / 2 CORRECT [GPT-2, Gemini-1]
    """
    correct_judges = []
    incorrect_judges = []
    failed_judges = []

    for judge in judge_details:
        judge_id = judge.get('judge_id', 'unknown')
        # Format judge_id nicely: gemini_1 -> Gemini-1
        formatted_id = judge_id.replace('_', '-').title()

        if judge.get('error'):
            failed_judges.append(formatted_id)
        elif judge.get('is_correct'):
            correct_judges.append(formatted_id)
        else:
            incorrect_judges.append(formatted_id)

    parts = []

    # Show the larger vote count first
    if len(incorrect_judges) >= len(correct_judges):
        if incorrect_judges:
            parts.append(f"{len(incorrect_judges)} INCORRECT [{', '.join(incorrect_judges)}]")
        if correct_judges:
            parts.append(f"{len(correct_judges)} CORRECT [{', '.join(correct_judges)}]")
    else:
        if correct_judges:
            parts.append(f"{len(correct_judges)} CORRECT [{', '.join(correct_judges)}]")
        if incorrect_judges:
            parts.append(f"{len(incorrect_judges)} INCORRECT [{', '.join(incorrect_judges)}]")

    if failed_judges:
        parts.append(f"{len(failed_judges)} failed [{', '.join(failed_judges)}]")

    return " / ".join(parts)


def format_judge_reasoning(judge: dict) -> str:
    """
    Format a single judge's reasoning for the log file.
    Extracts the key evaluation logic from their response.
    """
    judge_id = judge.get('judge_id', 'unknown').replace('_', '-').title()
    is_correct = judge.get('is_correct')
    reasoning = judge.get('reasoning', '')
    error = judge.get('error')

    if error:
        return f"      {judge_id}: FAILED - {error}"

    verdict = "CORRECT" if is_correct else "INCORRECT"

    # Clean up the reasoning
    reasoning = strip_markdown(reasoning)

    # Extract the most relevant part of the reasoning
    # Look for "Reasoning:" section or "Status:" line
    if "Reasoning:" in reasoning:
        reasoning = reasoning.split("Reasoning:")[-1].strip()
    elif "Status:" in reasoning:
        # Remove the status line, keep the rest
        lines = reasoning.split('\n')
        reasoning = '\n'.join(line for line in lines if not line.strip().startswith('Status:'))
        reasoning = reasoning.strip()

    # Truncate if too long but keep it meaningful
    if len(reasoning) > 400:
        # Try to cut at a sentence boundary
        truncated = reasoning[:400]
        last_period = truncated.rfind('.')
        if last_period > 200:
            reasoning = truncated[:last_period + 1]
        else:
            reasoning = truncated + "..."

    # Format with indentation
    return f"      {judge_id} [{verdict}]: {reasoning}"


def format_evaluator_output(consensus: dict, for_log: bool = True) -> str:
    """
    Format evaluator output for logging or console.

    Args:
        consensus: The consensus dict from ConsensusAgent
        for_log: If True, formats for log file with judge details. If False, formats for console.
    """
    lines = []

    vote_breakdown = consensus.get('vote_breakdown', {})
    judge_details = consensus.get('judge_details', [])

    # Vote breakdown with model names
    votes_str = format_vote_breakdown(vote_breakdown, judge_details)
    lines.append(f"    Votes: {votes_str}")

    # Verdict
    verdict = consensus.get('final_verdict', 'UNKNOWN')
    lines.append(f"    Verdict: {verdict}")

    # For log file, add each judge's reasoning
    if for_log and judge_details:
        lines.append("")
        lines.append("    Judge Evaluations:")
        for judge in judge_details:
            lines.append(format_judge_reasoning(judge))

    return '\n'.join(lines)
