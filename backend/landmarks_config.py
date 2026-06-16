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

# Sequential landmark indices tracing closed/open face contours (for Roto Spline generation)
CONTOUR_GROUPS = {
    "Face_Oval": [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
    "Lips_Outer": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146],
    "Lips_Inner": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95],
    "Left_Eye": [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398],
    "Right_Eye": [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
    "Left_Eyebrow": [336, 296, 334, 293, 300, 276, 283, 282, 295, 285],
    "Right_Eyebrow": [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
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
        
    result = {}
    for name in names:
        if name in ALL_LANDMARKS:
            result[name] = ALL_LANDMARKS[name]
        elif name.startswith("Mesh_"):
            try:
                idx = int(name.split("_")[1])
                if 0 <= idx < 468:
                    result[name] = idx
            except Exception:
                pass
        else:
            # Check if it matches a contour-based tracker name, e.g., Face_Oval_5
            for group_name, indices in CONTOUR_GROUPS.items():
                if name.startswith(group_name + "_"):
                    try:
                        idx_in_group = int(name.replace(group_name + "_", ""))
                        if 0 <= idx_in_group < len(indices):
                            result[name] = indices[idx_in_group]
                    except Exception:
                        pass
    return result

def get_contour_groups_by_names(names):
    """Returns a dictionary {group_name: [indices]} for the given names (or all contour groups if names is empty)."""
    if not names:
        return CONTOUR_GROUPS
    return {name: CONTOUR_GROUPS[name] for name in names if name in CONTOUR_GROUPS}

