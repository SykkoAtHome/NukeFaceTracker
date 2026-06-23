from typing import Dict, Tuple

# Full list of 52 ARKit blendshapes in the exact order emitted by MediaPipe FaceLandmarker.
# Index 0 is always '_neutral'.
ARKIT_BLENDSHAPE_NAMES: Tuple[str, ...] = (
    "_neutral",             # 0
    "browDownLeft",         # 1
    "browDownRight",        # 2
    "browInnerUp",          # 3
    "browOuterUpLeft",      # 4
    "browOuterUpRight",     # 5
    "cheekPuff",            # 6
    "cheekSquintLeft",      # 7
    "cheekSquintRight",     # 8
    "eyeBlinkLeft",         # 9
    "eyeBlinkRight",        # 10
    "eyeLookDownLeft",      # 11
    "eyeLookDownRight",     # 12
    "eyeLookInLeft",        # 13
    "eyeLookInRight",       # 14
    "eyeLookOutLeft",       # 15
    "eyeLookOutRight",      # 16
    "eyeLookUpLeft",        # 17
    "eyeLookUpRight",       # 18
    "eyeSquintLeft",        # 19
    "eyeSquintRight",       # 20
    "eyeWideLeft",          # 21
    "eyeWideRight",         # 22
    "jawForward",           # 23
    "jawLeft",              # 24
    "jawOpen",              # 25
    "jawRight",             # 26
    "mouthClose",           # 27
    "mouthDimpleLeft",      # 28
    "mouthDimpleRight",     # 29
    "mouthFrownLeft",       # 30
    "mouthFrownRight",      # 31
    "mouthFunnel",          # 32
    "mouthLeft",            # 33
    "mouthLowerDownLeft",   # 34
    "mouthLowerDownRight",  # 35
    "mouthPressLeft",       # 36
    "mouthPressRight",      # 37
    "mouthPucker",          # 38
    "mouthRight",           # 39
    "mouthRollLower",       # 40
    "mouthRollUpper",       # 41
    "mouthShrugLower",      # 42
    "mouthShrugUpper",      # 43
    "mouthSmileLeft",       # 44
    "mouthSmileRight",      # 45
    "mouthStretchLeft",     # 46
    "mouthStretchRight",    # 47
    "mouthUpperUpLeft",     # 48
    "mouthUpperUpRight",    # 49
    "noseSneerLeft",        # 50
    "noseSneerRight"        # 51
)

# Mapping of ARKit blendshapes to logical zones.
# Used for intensity sliders during Expression Retargeting.
BLENDSHAPE_ZONES: Dict[str, str] = {
    "_neutral": "neutral",
    
    # Brows
    "browDownLeft": "brows",
    "browDownRight": "brows",
    "browInnerUp": "brows",
    "browOuterUpLeft": "brows",
    "browOuterUpRight": "brows",
    
    # Eyes
    "eyeBlinkLeft": "eyes",
    "eyeBlinkRight": "eyes",
    "eyeLookDownLeft": "eyes",
    "eyeLookDownRight": "eyes",
    "eyeLookInLeft": "eyes",
    "eyeLookInRight": "eyes",
    "eyeLookOutLeft": "eyes",
    "eyeLookOutRight": "eyes",
    "eyeLookUpLeft": "eyes",
    "eyeLookUpRight": "eyes",
    "eyeSquintLeft": "eyes",
    "eyeSquintRight": "eyes",
    "eyeWideLeft": "eyes",
    "eyeWideRight": "eyes",
    
    # Mouth
    "mouthClose": "mouth",
    "mouthDimpleLeft": "mouth",
    "mouthDimpleRight": "mouth",
    "mouthFrownLeft": "mouth",
    "mouthFrownRight": "mouth",
    "mouthFunnel": "mouth",
    "mouthLeft": "mouth",
    "mouthLowerDownLeft": "mouth",
    "mouthLowerDownRight": "mouth",
    "mouthPressLeft": "mouth",
    "mouthPressRight": "mouth",
    "mouthPucker": "mouth",
    "mouthRight": "mouth",
    "mouthRollLower": "mouth",
    "mouthRollUpper": "mouth",
    "mouthShrugLower": "mouth",
    "mouthShrugUpper": "mouth",
    "mouthSmileLeft": "mouth",
    "mouthSmileRight": "mouth",
    "mouthStretchLeft": "mouth",
    "mouthStretchRight": "mouth",
    "mouthUpperUpLeft": "mouth",
    "mouthUpperUpRight": "mouth",
    
    # Other (Jaw, Cheek, Nose)
    "jawForward": "other",
    "jawLeft": "other",
    "jawOpen": "other",
    "jawRight": "other",
    "cheekPuff": "other",
    "cheekSquintLeft": "other",
    "cheekSquintRight": "other",
    "noseSneerLeft": "other",
    "noseSneerRight": "other"
}
