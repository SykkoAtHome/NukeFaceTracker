# Mapping of landmark indices from Google MediaPipe Face Mesh (0-477)
# to descriptive names for VFX artists in Foundry Nuke.

LANDMARK_GROUPS = {
    "Nose": {
        "Nose_Tip": 4,
        "Nose_Bridge": 168,
        "Nose_Bottom": 2,
        "Nose_Left_Alar": 129,
        "Nose_Right_Alar": 358
    },
    "Eyes": {
        "Left_Eye_Outer": 263,
        "Left_Eye_Inner": 362,
        "Left_Eye_Top": 386,
        "Left_Eye_Bottom": 374,
        "Right_Eye_Outer": 33,
        "Right_Eye_Inner": 133,
        "Right_Eye_Top": 159,
        "Right_Eye_Bottom": 145
    },
    "Eyebrows": {
        "Left_Eyebrow_Outer": 300,
        "Left_Eyebrow_Center": 334,
        "Left_Eyebrow_Inner": 336,
        "Right_Eyebrow_Outer": 70,
        "Right_Eyebrow_Center": 105,
        "Right_Eyebrow_Inner": 107
    },
    "Mouth": {
        "Mouth_Left_Corner": 291,
        "Mouth_Right_Corner": 61,
        "Mouth_Top_Lip": 0,
        "Mouth_Bottom_Lip": 17,
        "Mouth_Left_Inner_Corner": 308,
        "Mouth_Right_Inner_Corner": 78
    },
    "Face Shape": {
        "Chin": 152,
        "Forehead": 10,
        "Left_Cheek": 323,
        "Right_Cheek": 93,
        "Left_Jaw_Angle": 172,
        "Right_Jaw_Angle": 397
    }
}

# Flat dictionary for fast lookups
ALL_LANDMARKS = {}
for group_name, landmarks in LANDMARK_GROUPS.items():
    for name, idx in landmarks.items():
        ALL_LANDMARKS[name] = idx

# Reverse mapping (index -> name)
INDEX_TO_NAME = {idx: name for name, idx in ALL_LANDMARKS.items()}

def get_landmarks_by_names(names):
    """Returns a dictionary {name: index} for the given names (or all landmarks if names is empty)."""
    if not names:
        return ALL_LANDMARKS
    return {name: ALL_LANDMARKS[name] for name in names if name in ALL_LANDMARKS}
