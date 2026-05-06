import os
import io
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from PIL import Image
from utils import metrics


class SceneSynthesisAgent:
    def __init__(self, model_name="gemini-3-pro-image-preview"):
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        if not self.project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable not set.\n"
                "Set it with: export GOOGLE_CLOUD_PROJECT='your-gcp-project-id'\n"
                "Also run: gcloud auth application-default login"
            )
        self.client = genai.Client(vertexai=True, project=self.project, location=self.location)
        self.model_name = model_name

    def edit_image(self, image_path: str, action_json: dict, output_path: str = None) -> str:
        """
        Edits the image based on the action JSON using Gemini image generation on Vertex AI.
        Converts JSON to a natural language prompt.
        """
        try:
            base_img = Image.open(image_path)

            op = action_json.get("op", "modify")
            obj = action_json.get("object", "object")
            loc_desc = action_json.get("location_description", "")
            props = action_json.get("properties", {})
            relation = props.get("relation_to_target", "")
            material = props.get("material", "")
            color = props.get("color", "")

            prompt = f"Edit this image to {op.replace('_', ' ')}: a {color} {material} {obj}."

            if loc_desc:
                prompt += f" Position: It must be {loc_desc}."

            if relation:
                prompt += f" Relation: It should be {relation.replace('_', ' ')}."

            pos = action_json.get("position", {})
            if pos:
                prompt += f" Location Hint: roughly around coordinates x={pos.get('x')}, y={pos.get('y')}."

            prompt += " Make it look photorealistic and physically correct."
            prompt += (
                " STRICT EDITING CONSTRAINTS: Add ONLY the single object specified above."
                " Preserve every other object in the original image EXACTLY — do not delete,"
                " modify, duplicate, move, or alter the appearance of any pre-existing object."
                " The camera viewpoint, framing, lighting, and background must remain identical to the input image."
                " The output must look like the input image with one new object added — nothing else changed."
            )

            print(f"Sending edit request to {self.model_name} with prompt: {prompt}")

            max_retries = 5
            base_delay = 60

            response = None
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=[prompt, base_img],
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                        ),
                    )
                    metrics.record_call(self.model_name, is_image=True)
                    break
                except genai_errors.APIError as e:
                    code = getattr(e, "code", None)
                    if code == 429:
                        print(f"Rate limit hit (Attempt {attempt+1}/{max_retries}). Waiting {base_delay} seconds...")
                        time.sleep(base_delay)
                        base_delay *= 2
                    else:
                        print(f"API error during generation: {e}")
                        return ""
                except Exception as e:
                    print(f"Error during generation: {e}")
                    return ""
            else:
                print("Max retries reached. Skipping this image.")
                return ""

            if response is None:
                return ""

            parts = None
            if hasattr(response, "candidates") and response.candidates:
                parts = response.candidates[0].content.parts

            if parts:
                for part in parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        img_data = part.inline_data.data
                        img = Image.open(io.BytesIO(img_data))

                        if not output_path:
                            timestamp = int(time.time())
                            output_path = f"results/modified_{timestamp}.png"

                        img.save(output_path)
                        return output_path

            text_attr = getattr(response, "text", None)
            print(f"No image found in response. Text: {text_attr}")
            return ""

        except Exception as e:
            print(f"Error in SceneSynthesisAgent: {e}")
            return ""
