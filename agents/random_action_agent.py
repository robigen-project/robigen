"""Random Object Insertion Agent — baseline ablation.

Replaces the LLM-driven SemanticSceneCreationAgent with a non-LLM agent
that picks a random plausible object from a fixed list and proposes
adding it adjacent to the target.

Used to answer: "is the LLM-driven action proposer actually contributing,
or could a naive random insertion produce equivalent failures?"
"""

import random


# Per-task list of plausible everyday objects to randomly insert.
# Kept generic and household-mundane so renders satisfy basic plausibility.
RANDOM_OBJECT_POOL = [
    "small ceramic mug", "white plate", "kitchen towel", "glass jar",
    "plastic water bottle", "tin can", "yellow sticky note", "crumpled paper bag",
    "metal fork", "metal spoon", "small book", "cardboard box",
    "blue plastic cup", "paper napkin", "kitchen knife handle",
    "small glass vase", "red apple", "ripe banana", "small orange",
    "wooden coaster", "fabric placemat", "rolled-up newspaper",
    "small spice jar", "dish sponge", "rubber band ball",
]

LOCATION_TEMPLATES = [
    "directly adjacent to the {target}, slightly to the left",
    "directly adjacent to the {target}, slightly to the right",
    "in front of the {target}, partially overlapping the lower edge",
    "behind the {target}, partially visible",
    "resting on top of the {target}",
    "next to the {target}, almost touching it",
]


class RandomActionAgent:
    """Drop-in replacement for SemanticSceneCreationAgent that picks a
    random object + placement instead of using an LLM. Same external
    interface so it's swap-able in test_main.py."""

    def __init__(self, model_name: str = "random-baseline", enable_memory: bool = True, seed: int = None):
        # model_name kept for interface compatibility; we never call an LLM.
        self.model_name = model_name
        self.enable_memory = enable_memory
        self.history = []
        self.rejected_history = []
        self._rng = random.Random(seed)
        # Track previously-used object names so we don't propose the same
        # one twice in a row (cheap pseudo-exploration).
        self._used = set()

    def reset_memory(self):
        self.history = []
        self.rejected_history = []
        self._used = set()

    def register_result(self, action: dict, success: bool, feedback: str):
        if not self.enable_memory:
            return
        self.history.append({"action": action, "success": success, "feedback": feedback})

    def register_rejection(self, action: dict, rejection_reason: str):
        if not self.enable_memory:
            return
        self.rejected_history.append({"action": action, "rejection_reason": rejection_reason})

    def propose_edit(
        self,
        image_path: str,
        target_object: str,
        target_output: dict,
        evaluator_feedback: str,
        task_type: str = "pick_up",
        attribute: str = None,
    ) -> dict:
        # Pick an object that hasn't been used recently for this scenario.
        pool = [o for o in RANDOM_OBJECT_POOL if o not in self._used]
        if not pool:
            self._used.clear()
            pool = RANDOM_OBJECT_POOL[:]
        obj = self._rng.choice(pool)
        self._used.add(obj)

        location = self._rng.choice(LOCATION_TEMPLATES).format(target=target_object)

        return {
            "op": "add_object",
            "object": obj,
            "location_description": location,
            "position": {"x": self._rng.randint(0, 1000), "y": self._rng.randint(0, 1000)},
            "bbox": {"width": 100, "height": 100},
            "rotation_deg": 0,
            "properties": {
                "material": "everyday",
                "color": "neutral",
                "relation_to_target": "near",
                "falsification_logic": "random baseline insertion (no LLM reasoning)",
            },
        }
