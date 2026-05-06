"""
Consensus Evaluator - Multi-Judge Voting System

Uses 6 independent judges (3 Gemini + 3 GPT) voting sequentially.

Meta-Combiner aggregates votes using majority rule (>=4 agreement).
Judges return structured JSON with verdict, confidence, significance, and reasoning.
"""

import os
import time
import json
import base64
from abc import ABC, abstractmethod
from PIL import Image

from config.tasks import get_task_config, get_evaluation_instructions
from utils import metrics


# Linear backoff schedule for judge API calls (10s, 15s, 20s, 25s, 30s, 35s, 40s).
# Hits ~175s max wait per failing judge before we give up.
JUDGE_RETRY_DELAYS = [10, 15, 20, 25, 30, 35, 40]


def _judge_call_with_retry(call_fn, judge_id: str):
    """Call a judge API function with linear backoff. Retries on any exception.

    Returns the call_fn's result on success.
    Re-raises the last exception if all retries fail.
    """
    last_exc = None
    for attempt, delay in enumerate(JUDGE_RETRY_DELAYS, 1):
        try:
            return call_fn()
        except Exception as e:
            last_exc = e
            if attempt < len(JUDGE_RETRY_DELAYS):
                print(f"            {judge_id} attempt {attempt} failed: {str(e)[:80]} | retry in {delay}s",
                      flush=True)
                time.sleep(delay)
            else:
                print(f"            {judge_id} attempt {attempt} failed (final): {str(e)[:80]}",
                      flush=True)
    raise last_exc


# ============================================================================
# Helper Functions
# ============================================================================

def image_to_base64(image_path: str) -> str:
    """Convert an image file to base64 string."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """Get the MIME type based on file extension."""
    ext = image_path.lower().split('.')[-1]
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    return mime_types.get(ext, 'image/jpeg')


def _parse_judge_response(text: str) -> dict:
    """
    Parse a judge's response, trying JSON first, then falling back to substring matching.

    Returns:
        dict with keys: verdict (str), confidence (int), significance (int), reasoning (str)
    """
    text = text.strip()

    # Clean markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try JSON parsing first
    try:
        parsed = json.loads(text)
        return {
            "verdict": parsed.get("verdict", "INCORRECT").upper(),
            "confidence": int(parsed.get("confidence", 5)),
            "significance": int(parsed.get("significance", 5)),
            "reasoning": parsed.get("reasoning", "")
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract JSON from mixed text
    import re
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            return {
                "verdict": parsed.get("verdict", "INCORRECT").upper(),
                "confidence": int(parsed.get("confidence", 5)),
                "significance": int(parsed.get("significance", 5)),
                "reasoning": parsed.get("reasoning", "")
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: substring matching (legacy behavior)
    is_correct = "Status: CORRECT" in text or '"verdict": "CORRECT"' in text
    return {
        "verdict": "CORRECT" if is_correct else "INCORRECT",
        "confidence": 5,
        "significance": 5,
        "reasoning": text
    }


# ============================================================================
# Base Judge Class
# ============================================================================

class BaseJudge(ABC):
    """Abstract base class for evaluation judges."""

    def __init__(self, judge_id: str):
        self.judge_id = judge_id
        self._validate_api_key()

    @abstractmethod
    def _validate_api_key(self):
        """Validate that the required API key is set."""
        pass

    @abstractmethod
    def evaluate_sync(self, image_path: str, eval_prompt: str) -> dict:
        """
        Synchronous evaluation - called within thread pool.

        Returns:
            dict with keys: 'is_correct' (bool), 'reasoning' (str), 'judge_id' (str),
                           'confidence' (int), 'significance' (int)
        """
        pass


# ============================================================================
# Gemini Judge
# ============================================================================

class GeminiJudge(BaseJudge):
    """Judge using Google's Gemini model on Vertex AI."""

    def __init__(self, judge_id: str, model_name: str = "gemini-2.5-flash", temperature: float = 0.0):
        self.model_name = model_name
        self.temperature = temperature
        super().__init__(judge_id)

    def _validate_api_key(self):
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        if not self.project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT not set for Gemini judge.\n"
                "Set it with: export GOOGLE_CLOUD_PROJECT='your-gcp-project-id'\n"
                "Also run: gcloud auth application-default login"
            )

    def evaluate_sync(self, image_path: str, eval_prompt: str) -> dict:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )
        img = Image.open(image_path)

        def make_request():
            response = client.models.generate_content(
                model=self.model_name,
                contents=[eval_prompt, img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=self.temperature,
                ),
            )
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                metrics.record_call(
                    self.model_name,
                    input_tokens=getattr(usage, "prompt_token_count", None),
                    output_tokens=getattr(usage, "candidates_token_count", None),
                )
            return response

        try:
            response = _judge_call_with_retry(make_request, self.judge_id)
            parsed = _parse_judge_response(response.text.strip())
            return {
                "judge_id": self.judge_id,
                "model": "gemini",
                "is_correct": parsed["verdict"] == "CORRECT",
                "confidence": parsed["confidence"],
                "significance": parsed["significance"],
                "reasoning": parsed["reasoning"],
                "error": None
            }
        except Exception as e:
            return {
                "judge_id": self.judge_id,
                "model": "gemini",
                "is_correct": None,
                "confidence": None,
                "significance": None,
                "reasoning": None,
                "error": str(e)
            }


# ============================================================================
# GPT Judge
# ============================================================================

class GPTJudge(BaseJudge):
    """Judge using OpenAI's GPT-4o model."""

    def __init__(self, judge_id: str, model_name: str = "gpt-4o", temperature: float = 0.0):
        self.model_name = model_name
        self.temperature = temperature
        super().__init__(judge_id)

    def _validate_api_key(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set for GPT judge")

    def evaluate_sync(self, image_path: str, eval_prompt: str) -> dict:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        base64_image = image_to_base64(image_path)
        mime_type = get_image_mime_type(image_path)

        def make_request():
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": eval_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                max_tokens=1024,
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                metrics.record_call(
                    self.model_name,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                )
            return response

        try:
            response = _judge_call_with_retry(make_request, self.judge_id)
            text = response.choices[0].message.content.strip()
            parsed = _parse_judge_response(text)
            return {
                "judge_id": self.judge_id,
                "model": "gpt",
                "is_correct": parsed["verdict"] == "CORRECT",
                "confidence": parsed["confidence"],
                "significance": parsed["significance"],
                "reasoning": parsed["reasoning"],
                "error": None
            }
        except Exception as e:
            return {
                "judge_id": self.judge_id,
                "model": "gpt",
                "is_correct": None,
                "confidence": None,
                "significance": None,
                "reasoning": None,
                "error": str(e)
            }


# ============================================================================
# Meta-Combiner
# ============================================================================

class MetaCombiner:
    """
    Aggregates votes from multiple judges and produces final verdict.

    Majority rule: >=4 out of 6 votes required for consensus.
    If a judge fails (error), it's excluded from the count.
    """

    MAJORITY_THRESHOLD = 4  # Minimum votes needed for consensus

    def combine(self, judge_results: list[dict]) -> dict:
        """
        Combine judge results into final verdict.

        Args:
            judge_results: List of dicts from each judge

        Returns:
            dict with final verdict and detailed breakdown
        """
        # Filter out failed judges
        valid_results = [r for r in judge_results if r["error"] is None]
        failed_results = [r for r in judge_results if r["error"] is not None]

        # Count votes
        correct_votes = sum(1 for r in valid_results if r["is_correct"])
        incorrect_votes = sum(1 for r in valid_results if not r["is_correct"])
        total_valid = len(valid_results)

        # Determine majority verdict
        if total_valid == 0:
            # All judges failed
            return {
                "final_verdict": None,
                "is_correct": False,  # Default to incorrect if all fail
                "confidence": 0.0,
                "average_significance": 0,
                "vote_breakdown": {
                    "correct": 0,
                    "incorrect": 0,
                    "failed": len(failed_results),
                    "total": len(judge_results)
                },
                "consensus_reached": False,
                "needs_human_review": True,
                "reasoning": "All judges failed to evaluate. Defaulting to INCORRECT.",
                "judge_details": judge_results
            }

        # Check for majority
        if correct_votes >= self.MAJORITY_THRESHOLD:
            final_is_correct = True
            confidence = correct_votes / total_valid
        elif incorrect_votes >= self.MAJORITY_THRESHOLD:
            final_is_correct = False
            confidence = incorrect_votes / total_valid
        else:
            # No clear majority — use confidence-weighted tiebreak
            # Sum confidence scores per side; higher total wins
            correct_confidence_sum = sum(
                r.get("confidence", 5) for r in valid_results if r["is_correct"]
            )
            incorrect_confidence_sum = sum(
                r.get("confidence", 5) for r in valid_results if not r["is_correct"]
            )
            final_is_correct = correct_confidence_sum >= incorrect_confidence_sum
            confidence = max(correct_votes, incorrect_votes) / total_valid

        consensus_reached = max(correct_votes, incorrect_votes) >= self.MAJORITY_THRESHOLD

        # Flag borderline cases (3-3 split or near-split)
        needs_human_review = not consensus_reached

        # Compute average significance from INCORRECT-voting judges
        incorrect_judges = [r for r in valid_results if not r["is_correct"]]
        if incorrect_judges:
            sig_values = [r.get("significance", 5) for r in incorrect_judges if r.get("significance") is not None]
            average_significance = sum(sig_values) / len(sig_values) if sig_values else 5
        else:
            average_significance = 0

        # Synthesize reasoning from majority
        majority_results = [r for r in valid_results if r["is_correct"] == final_is_correct]
        synthesized_reasoning = self._synthesize_reasoning(
            final_is_correct,
            correct_votes,
            incorrect_votes,
            total_valid,
            majority_results,
            failed_results
        )

        return {
            "final_verdict": "CORRECT" if final_is_correct else "INCORRECT",
            "is_correct": final_is_correct,
            "confidence": confidence,
            "average_significance": round(average_significance, 1),
            "vote_breakdown": {
                "correct": correct_votes,
                "incorrect": incorrect_votes,
                "failed": len(failed_results),
                "total": len(judge_results),
                "correct_confidence_sum": sum(r.get("confidence", 5) for r in valid_results if r["is_correct"]),
                "incorrect_confidence_sum": sum(r.get("confidence", 5) for r in valid_results if not r["is_correct"]),
            },
            "consensus_reached": consensus_reached,
            "needs_human_review": needs_human_review,
            "reasoning": synthesized_reasoning,
            "judge_details": judge_results
        }

    def _synthesize_reasoning(
        self,
        final_is_correct: bool,
        correct_votes: int,
        incorrect_votes: int,
        total_valid: int,
        majority_results: list[dict],
        failed_results: list[dict]
    ) -> str:
        """Synthesize a unified reasoning from majority judges."""
        verdict = "CORRECT" if final_is_correct else "INCORRECT"
        majority_count = correct_votes if final_is_correct else incorrect_votes

        # Build summary
        lines = [
            f"CONSENSUS VERDICT: {verdict}",
            f"Vote Count: {majority_count}/{total_valid} judges agree ({majority_count/total_valid*100:.0f}% confidence)",
            ""
        ]

        if failed_results:
            lines.append(f"Note: {len(failed_results)} judge(s) failed to respond.")
            lines.append("")

        # Include key points from majority judges
        lines.append("Key observations from majority judges:")
        for i, result in enumerate(majority_results[:3], 1):  # Limit to 3 to keep it concise
            reasoning = result.get("reasoning", "")
            # Take first 200 chars
            snippet = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            lines.append(f"  [{result['model'].upper()}] {snippet}")

        return "\n".join(lines)


# ============================================================================
# Consensus Evaluator (Main Class)
# ============================================================================

class ConsensusAgent:
    """
    Consensus-based evaluator using 6 independent judges.

    3 Gemini + 3 GPT = 6 total votes.
    Judges return structured JSON with verdict, confidence, significance, and reasoning.
    Evaluations run sequentially for stability.
    """

    def __init__(self):
        """Initialize all 6 judges."""
        self.judges = []
        self._init_judges()
        self.combiner = MetaCombiner()
        print(f"ConsensusAgent initialized with {len(self.judges)} judges")

    def _init_judges(self):
        """Initialize the 6 judges (3 Gemini x 3 GPT)."""
        # Track which judges are available
        available_judges = []

        # Gemini judges with distinct temperatures so the 3 calls produce
        # genuinely different samples instead of identical deterministic output.
        try:
            self.judges.append(GeminiJudge("gemini_1", temperature=0.0))
            self.judges.append(GeminiJudge("gemini_2", temperature=0.4))
            self.judges.append(GeminiJudge("gemini_3", temperature=0.8))
            available_judges.append("Gemini x3")
        except ValueError as e:
            print(f"Warning: Gemini judges unavailable - {e}")

        # GPT judges with distinct temperatures (same reason as above).
        try:
            self.judges.append(GPTJudge("gpt_1", temperature=0.0))
            self.judges.append(GPTJudge("gpt_2", temperature=0.4))
            self.judges.append(GPTJudge("gpt_3", temperature=0.8))
            available_judges.append("GPT x3")
        except ValueError as e:
            print(f"Warning: GPT judges unavailable - {e}")

        if not self.judges:
            raise ValueError(
                "No judges available! Set at least one of: "
                "GOOGLE_CLOUD_PROJECT (with ADC), OPENAI_API_KEY"
            )

        print(f"  Available judges: {', '.join(available_judges)}")

    def _build_eval_prompt(
        self,
        prompt: str,
        target_output: dict,
        task_type: str,
        target_object: str = None,
        attribute: str = None
    ) -> str:
        """Build the evaluation prompt for judges."""
        task_config = get_task_config(task_type)
        criteria = task_config["evaluation_criteria"]

        # Format criteria as guidance points
        criteria_str = "\n".join([f"  - {c}" for c in criteria])

        # Format target output
        target_str = self._format_target_output(task_type, target_output)

        # Get detailed evaluation instructions
        eval_instructions = get_evaluation_instructions(task_type, target_object, attribute)

        eval_prompt = f"""You are an expert evaluator for robotic vision systems.

Original Prompt: {prompt}

Target Model Output: {target_str}

Look at the image and determine if the Target Model Output is correct and accurate.
Reason and understand the context of the image and the prompt.
Check if the reasoning logic makes sense for the task.

Evaluation Criteria:
{criteria_str}

Detailed Instructions:
{eval_instructions}

IMPORTANT: If the answer is borderline or you are unsure, default to CORRECT — only mark INCORRECT when there is a clear, significant error that would cause a real problem for a robot.

You MUST respond ONLY with a JSON object in this exact format:
{{
  "verdict": "CORRECT" or "INCORRECT",
  "confidence": <1-10 how confident you are in your verdict>,
  "significance": <1-10 how significant the error is, where 1=trivial and 10=safety-critical. Set to 0 if verdict is CORRECT>,
  "reasoning": "Your detailed reasoning"
}}
"""
        return eval_prompt

    def _format_target_output(self, task_type: str, target_output: dict) -> str:
        """Format the target output for evaluation based on task type."""
        if task_type == "pick_up":
            location = target_output.get('location', 'N/A')
            reason = target_output.get('reason', 'N/A')
            return f"Location: {location}\nReasoning: {reason}"

        elif task_type == "detection":
            count = target_output.get('count', 'N/A')
            reason = target_output.get('reason', 'N/A')
            return f"Count: {count}, Reason: {reason}"

        elif task_type == "ambiguity":
            is_unique = target_output.get('is_unique', 'N/A')
            candidates = target_output.get('candidates', [])
            clarification = target_output.get('clarification_question', 'N/A')
            reason = target_output.get('reason', 'N/A')
            return (
                f"Is Unique: {is_unique}\n"
                f"Candidates: {candidates}\n"
                f"Clarification Question: {clarification}\n"
                f"Reason: {reason}"
            )

        elif task_type == "attribute":
            answer = target_output.get('answer', 'N/A')
            reason = target_output.get('reason', 'N/A')
            return f"Answer: {answer}, Reason: {reason}"

        # Fallback: dump as JSON
        return json.dumps(target_output, indent=2)

    def evaluate(
        self,
        image_path: str,
        prompt: str,
        target_output: dict,
        task_type: str = "pick_up",
        target_object: str = None,
        attribute: str = None
    ) -> tuple[bool, str]:
        """
        Evaluate using consensus of multiple judges.

        Args:
            image_path: Path to the image file
            prompt: The original prompt sent to the target model
            target_output: The target model's response
            task_type: One of 'pick_up', 'detection', 'ambiguity', 'attribute'
            target_object: The target object (for evaluation instructions)
            attribute: The attribute being tested (for 'attribute' task)

        Returns:
            Tuple of (is_correct: bool, reasoning: str)
        """
        # Build evaluation prompt
        eval_prompt = self._build_eval_prompt(
            prompt, target_output, task_type, target_object, attribute
        )

        # Run judges sequentially (more stable than parallel)
        print(f"        Running {len(self.judges)} judges...")

        results = []
        for judge in self.judges:
            print(f"          - {judge.judge_id}...", end=" ", flush=True)
            try:
                result = judge.evaluate_sync(image_path, eval_prompt)
                results.append(result)
                verdict = "CORRECT" if result.get('is_correct') else "INCORRECT"
                print(verdict)
            except Exception as e:
                results.append({
                    "judge_id": judge.judge_id,
                    "model": getattr(judge, 'model_name', 'unknown'),
                    "is_correct": None,
                    "confidence": None,
                    "significance": None,
                    "reasoning": None,
                    "error": str(e)
                })
                print(f"FAILED ({str(e)[:30]})")

        # Combine votes
        consensus = self.combiner.combine(results)

        # Print vote breakdown with model names
        correct_judges = [r['judge_id'].replace('_', '-').title() for r in results if r.get('is_correct') and not r.get('error')]
        incorrect_judges = [r['judge_id'].replace('_', '-').title() for r in results if not r.get('is_correct') and not r.get('error')]
        failed_judges = [r['judge_id'].replace('_', '-').title() for r in results if r.get('error')]

        vote_parts = []
        if len(correct_judges) >= len(incorrect_judges):
            if correct_judges:
                vote_parts.append(f"{len(correct_judges)} CORRECT [{', '.join(correct_judges)}]")
            if incorrect_judges:
                vote_parts.append(f"{len(incorrect_judges)} INCORRECT [{', '.join(incorrect_judges)}]")
        else:
            if incorrect_judges:
                vote_parts.append(f"{len(incorrect_judges)} INCORRECT [{', '.join(incorrect_judges)}]")
            if correct_judges:
                vote_parts.append(f"{len(correct_judges)} CORRECT [{', '.join(correct_judges)}]")
        if failed_judges:
            vote_parts.append(f"{len(failed_judges)} failed")

        print(f"        Votes: {' / '.join(vote_parts)}")
        print(f"        Verdict: {consensus['final_verdict']}")

        if consensus.get("needs_human_review"):
            vb = consensus.get("vote_breakdown", {})
            c_conf = vb.get("correct_confidence_sum", 0)
            i_conf = vb.get("incorrect_confidence_sum", 0)
            print(f"        ⚠ TIEBREAK — confidence sums: CORRECT={c_conf} vs INCORRECT={i_conf}")

        # Store full consensus data for logging
        self.last_consensus = consensus

        return consensus["is_correct"], consensus["reasoning"]

    def get_last_consensus_details(self) -> dict:
        """Get detailed results from the last evaluation."""
        return getattr(self, 'last_consensus', None)
