import os
import json
from google import genai
from google.genai import types
from PIL import Image
from config.tasks import get_task_config, get_evaluation_instructions
from utils import metrics


class EvaluationAgent:
    def __init__(self, model_name="gemini-flash-latest"):
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        if not self.project:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set")
        self.client = genai.Client(vertexai=True, project=self.project, location=self.location)
        self.model_name = model_name

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
        Evaluates if the target_output is correct for the given image and task.

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
        try:
            img = Image.open(image_path)

            # Get task config for criteria
            task_config = get_task_config(task_type)
            criteria = task_config["evaluation_criteria"]

            # Format criteria as guidance points
            criteria_str = "\n".join([f"  - {c}" for c in criteria])

            # Format target output for the evaluator based on task type
            target_str = self._format_target_output(task_type, target_output)

            eval_prompt = f"""You are an expert evaluator.

Original Prompt: {prompt}

Target Model Output: {target_str}

Look at the image and determine if the Target Model Output is correct and accurate.
Reason and understand the context of the image and the prompt.
Check if the reasoning logic makes sense for the task.

Consider the following criteria as guidance (not a strict checklist):
{criteria_str}

Focus on whether the TARGET OBJECT was correctly identified and if the REASONING is sound.

Respond with CORRECT or INCORRECT followed by your reasoning.
Format:
Status: [CORRECT/INCORRECT]
Reasoning: [Your reasoning]
"""
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[eval_prompt, img],
            )
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                metrics.record_call(
                    self.model_name,
                    input_tokens=getattr(usage, "prompt_token_count", None),
                    output_tokens=getattr(usage, "candidates_token_count", None),
                )
            text = response.text.strip()

            is_correct = "Status: CORRECT" in text
            return is_correct, text

        except Exception as e:
            print(f"Error in EvaluationAgent: {e}")
            return False, f"Error: {e}"

    def _format_target_output(self, task_type: str, target_output: dict) -> str:
        """
        Formats the target output for evaluation based on task type.

        Args:
            task_type: The type of task
            target_output: The target model's response

        Returns:
            Formatted string representation of the output
        """
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
