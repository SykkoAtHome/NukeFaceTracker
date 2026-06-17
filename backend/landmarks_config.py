# Mapping of landmark indices from Google MediaPipe Face Mesh (0-477)
# to descriptive names for VFX artists in Foundry Nuke.

# --- SPARSE LANDMARK GROUPS ---
LANDMARK_GROUPS = {
    "Nose": {
        "Nose_Tip": 4,
        "Nose_Bridge": 168,
        "Nose_Bottom": 2,
        "Nose_Left_Alar": 358,   # Corrected: person's left (viewer's right)
        "Nose_Right_Alar": 129,  # Corrected: person's right (viewer's left)
        "Nose_Columella": 1,
        "Nose_Subnasale": 2
    },
    "Eyes": {
        "Left_Eye_Outer": 263,
        "Left_Eye_Inner": 362,
        "Left_Eye_Top": 386,
        "Left_Eye_Bottom": 374,
        "Right_Eye_Outer": 33,
        "Right_Eye_Inner": 133,
        "Right_Eye_Top": 159,
        "Right_Eye_Bottom": 145,
        "Left_Iris_Center": 468,
        "Right_Iris_Center": 473
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

# --- DENSE CONTOUR GROUPS (Sequential tracker indices tracing face features) ---
CONTOUR_GROUPS = {
    "Face_Oval": [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
    "Lips_Outer": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146],
    "Lips_Inner": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95],
    "Left_Eye": [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398],
    "Right_Eye": [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
    "Left_Eyebrow": [336, 296, 334, 293, 300, 276, 283, 282, 295, 285],
    "Right_Eyebrow": [70, 63, 105, 66, 107, 55, 65, 52, 53, 46],
    # --- New Premium Contours ---
    "Left_Iris": [469, 470, 471, 472],
    "Right_Iris": [474, 475, 476, 477],
    "Nose_Bridge_Contour": [6, 197, 195, 5, 168],
    "Nose_Left_Nostril": [458, 250, 290, 305, 392, 309],
    "Nose_Right_Nostril": [75, 60, 20, 238, 79, 166],
    "Left_Cheek_Bone": [454, 356, 389],
    "Right_Cheek_Bone": [234, 127, 162]
}

DENSE_PART_TO_CONTOURS = {
    "Nose": ["Nose_Bridge_Contour", "Nose_Left_Nostril", "Nose_Right_Nostril"],
    "Eyes": ["Left_Eye", "Right_Eye", "Left_Iris", "Right_Iris"],
    "Eyebrows": ["Left_Eyebrow", "Right_Eyebrow"],
    "Mouth": ["Lips_Outer", "Lips_Inner"],
    "Face Shape": ["Face_Oval", "Left_Cheek_Bone", "Right_Cheek_Bone"],
}

OPEN_CONTOUR_GROUPS = {
    "Nose_Bridge_Contour",
}

# --- FULL MESH PARTITION INDICES (Strict mathematical subsets of all 478 landmarks) ---
EYEBROWS_MESH_INDICES = [46, 52, 53, 55, 63, 65, 66, 70, 105, 107, 276, 282, 283, 285, 293, 295, 296, 300, 334, 336]

EYES_MESH_INDICES = [
    7, 22, 23, 24, 33, 110, 130, 133, 144, 145, 153, 154, 155, 157, 158, 159, 160, 161, 163, 173,
    246, 247, 249, 250, 251, 252, 253, 254, 256, 263, 339, 341, 359, 362, 373, 374, 380, 381, 382,
    384, 385, 386, 387, 388, 390, 398, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477
]

LIPS_MESH_INDICES = [
    0, 11, 12, 13, 14, 15, 16, 17, 37, 38, 39, 40, 41, 42, 61, 62, 72, 73, 74, 76, 77, 78, 80, 81,
    82, 84, 85, 86, 87, 88, 91, 95, 96, 146, 178, 179, 180, 181, 183, 184, 185, 191, 267, 268, 269,
    270, 271, 272, 291, 292, 302, 303, 304, 306, 307, 308, 310, 311, 312, 314, 315, 316, 317, 318,
    321, 324, 325, 375, 402, 403, 404, 405, 407, 408, 409, 415
]

NOSE_MESH_INDICES = [
    1, 2, 3, 4, 5, 6, 48, 49, 64, 97, 98, 102, 114, 115, 122, 129, 131, 141, 168, 193, 195, 196, 197,
    198, 209, 217, 218, 219, 220, 278, 279, 294, 326, 327, 331, 343, 344, 351, 358, 360, 370, 399,
    417, 419, 420, 429, 437, 438, 439, 440
]

# Face shape contains all indices in 0..477 that are not part of eyebrows, eyes, lips, or nose
FACE_SHAPE_MESH_INDICES = sorted(list(set(range(478)) - set(EYEBROWS_MESH_INDICES) - set(EYES_MESH_INDICES) - set(LIPS_MESH_INDICES) - set(NOSE_MESH_INDICES)))


# --- DYNAMIC LANDMARK RESOLVER ---
def get_landmarks_for_density(density, active_parts):
    """
    Returns a resolved dictionary of {landmark_name: index} based on density level
    and list of active parts selected by the user.
    """
    resolved = {}
    active_set = set(active_parts)

    if "Sparse" in density:
        for part, landmarks in LANDMARK_GROUPS.items():
            if part in active_set:
                for name, idx in landmarks.items():
                    resolved[name] = idx

    elif "Dense" in density:
        if "Nose" in active_set:
            for name, idx in LANDMARK_GROUPS["Nose"].items():
                resolved[name] = idx

        for part, contour_names in DENSE_PART_TO_CONTOURS.items():
            if part in active_set:
                for contour_name in contour_names:
                    pts = CONTOUR_GROUPS[contour_name]
                    for i, idx in enumerate(pts):
                        resolved[f"{contour_name}_{i}"] = idx

    elif "Full" in density:
        part_to_mesh_indices = {
            "Nose": NOSE_MESH_INDICES,
            "Eyes": EYES_MESH_INDICES,
            "Eyebrows": EYEBROWS_MESH_INDICES,
            "Mouth": LIPS_MESH_INDICES,
            "Face Shape": FACE_SHAPE_MESH_INDICES
        }
        for part, indices in part_to_mesh_indices.items():
            if part in active_set:
                for idx in indices:
                    resolved[f"Mesh_{idx}"] = idx

    return resolved


# Flat dictionary of all individual landmarks for quick lookup
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
                if 0 <= idx < 478:  # Extended to support 478 landmarks (including Iris)
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
