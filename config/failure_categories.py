"""
Failure mode taxonomy for categorizing successful adversarial attacks.

Each category has keywords used for automatic classification based on
the action agent's output (op, object, falsification_logic).
"""

FAILURE_CATEGORIES = {
    "transparent_object": {
        "name": "Transparent Object Confusion",
        "description": "VLM fails due to transparent/reflective objects or barriers",
        "keywords": ["glass", "transparent", "clear", "plastic", "see-through", "acrylic",
                     "translucent", "crystal", "perspex", "plexiglass", "barrier"]
    },
    "occlusion": {
        "name": "Occlusion Failure",
        "description": "VLM fails when target is partially hidden or blocked",
        "keywords": ["occlude", "block", "behind", "hidden", "covered", "obscure",
                     "stack", "pile", "in front of", "obstruct"]
    },
    "color_confusion": {
        "name": "Color/Appearance Confusion",
        "description": "VLM confused by similar colors or visual appearances",
        "keywords": ["color", "similar", "look-alike", "camouflage", "blend",
                     "match", "same color", "identical", "indistinguishable"]
    },
    "scale_distortion": {
        "name": "Scale Distortion",
        "description": "VLM fails with unexpected object scales or sizes",
        "keywords": ["scale", "size", "miniature", "giant", "resize", "tiny",
                     "oversized", "undersized", "proportion"]
    },
    "duplicate_decoy": {
        "name": "Duplicate/Decoy Confusion",
        "description": "VLM confused by duplicate or very similar objects",
        "keywords": ["duplicate", "clone", "copy", "decoy", "twin", "replica",
                     "double", "multiple", "doppelganger", "identical"]
    },
    "context_mismatch": {
        "name": "Context Mismatch",
        "description": "VLM misled by objects placed in unexpected contexts",
        "keywords": ["context", "mismatch", "unexpected", "out of place", "wrong location",
                     "misplaced", "unusual", "incongruous"]
    },
    "lighting_shadow": {
        "name": "Lighting/Shadow Manipulation",
        "description": "VLM fails under adversarial lighting or shadow conditions",
        "keywords": ["lighting", "shadow", "highlight", "dark", "bright", "glare",
                     "spotlight", "dim", "overexpose", "underexpose"]
    },
    "reflection": {
        "name": "Reflection Deception",
        "description": "VLM confused by reflections, mirrors, or reflective surfaces",
        "keywords": ["reflect", "mirror", "surface", "shiny", "metallic", "chrome",
                     "polished", "glossy"]
    },
    "physical_constraint": {
        "name": "Physical Constraint Ignorance",
        "description": "VLM ignores physical constraints (enclosed, wedged, inaccessible)",
        "keywords": ["enclosed", "sealed", "locked", "wedge", "stuck", "trapped",
                     "inaccessible", "unreachable", "constraint", "barrier",
                     "box", "case", "container", "cage"]
    },
    "texture_material": {
        "name": "Texture/Material Confusion",
        "description": "VLM confused by surface texture or material changes",
        "keywords": ["texture", "material", "surface", "fabric", "wood", "metal",
                     "painted", "wrapped", "coated", "disguised"]
    },
}
