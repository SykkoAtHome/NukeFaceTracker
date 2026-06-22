import json
import os
import re

# Mapping of landmark indices from Google MediaPipe Face Mesh (0-477)
# to descriptive names for VFX artists in Foundry Nuke.

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MAPPING_PATH = os.path.join(PLUGIN_DIR, "default_mapping.json")

def hex_to_rgb(hex_str):
    if not hex_str:
        return None
    hex_str = hex_str.lstrip('#')
    try:
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16) / 255.0
            g = int(hex_str[2:4], 16) / 255.0
            b = int(hex_str[4:6], 16) / 255.0
            return [r, g, b, 1.0]
        elif len(hex_str) == 8:
            r = int(hex_str[0:2], 16) / 255.0
            g = int(hex_str[2:4], 16) / 255.0
            b = int(hex_str[4:6], 16) / 255.0
            a = int(hex_str[6:8], 16) / 255.0
            return [r, g, b, a]
    except Exception:
        pass
    return None

ROTO_CONTOUR_COLORS = {}

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

SPARSE_PART_TO_LANDMARKS = LANDMARK_GROUPS

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

NOSE_CONTOUR_GROUP_NAMES = ("Nose_Bridge_Contour", "Nose_Left_Nostril", "Nose_Right_Nostril")
EYE_CONTOUR_GROUP_NAMES = ("Left_Eye", "Right_Eye", "Left_Iris", "Right_Iris")
EYEBROW_CONTOUR_GROUP_NAMES = ("Left_Eyebrow", "Right_Eyebrow")
MOUTH_CONTOUR_GROUP_NAMES = ("Lips_Outer", "Lips_Inner")
FACE_SHAPE_CONTOUR_GROUP_NAMES = ("Face_Oval", "Left_Cheek_Bone", "Right_Cheek_Bone")

DENSE_PART_TO_CONTOURS = {
    "Nose": NOSE_CONTOUR_GROUP_NAMES,
    "Eyes": EYE_CONTOUR_GROUP_NAMES,
    "Eyebrows": EYEBROW_CONTOUR_GROUP_NAMES,
    "Mouth": MOUTH_CONTOUR_GROUP_NAMES,
    "Face Shape": FACE_SHAPE_CONTOUR_GROUP_NAMES,
}

# Roto intentionally exposes only spline-friendly facial feature contours.
# Surface groups below are tracker-only point clouds and must not be exported as Roto shapes.
ROTO_CONTOUR_GROUP_NAMES = (
    "Face_Oval",
    "Nose_Bridge_Contour",
    "Nose_Left_Nostril",
    "Nose_Right_Nostril",
    "Lips_Outer",
    "Lips_Inner",
    "Left_Eye",
    "Right_Eye",
    "Left_Iris",
    "Right_Iris",
    "Left_Eyebrow",
    "Right_Eyebrow",
)

ROTO_CONTOUR_KNOB_SPECS = (
    ("roto_oval", "Face_Oval", "Face Oval (36 pts)       ", True),
    ("roto_nose_bridge", "Nose_Bridge_Contour", "Nose Bridge (5 pts)", False),
    ("roto_left_nostril", "Nose_Left_Nostril", "Left Nostril (6 pts)     ", False),
    ("roto_right_nostril", "Nose_Right_Nostril", "Right Nostril (6 pts)", False),
    ("roto_lips_outer", "Lips_Outer", "Lips Outer (20 pts)      ", True),
    ("roto_lips_inner", "Lips_Inner", "Lips Inner (20 pts)", False),
    ("roto_left_eye", "Left_Eye", "Left Eye (16 pts)        ", False),
    ("roto_right_eye", "Right_Eye", "Right Eye (16 pts)", False),
    ("roto_left_iris", "Left_Iris", "Left Iris (4 pts)          ", False),
    ("roto_right_iris", "Right_Iris", "Right Iris (4 pts)", False),
    ("roto_left_eyebrow", "Left_Eyebrow", "Left Eyebrow (10 pts)   ", False),
    ("roto_right_eyebrow", "Right_Eyebrow", "Right Eyebrow (10 pts)", False),
)

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

NOSE_SURFACE_INDICES = [
    1, 2, 3, 4, 5, 6, 45, 48, 64, 97, 98, 115, 122, 129, 131, 168, 193, 195, 197, 220,
    275, 278, 294, 326, 327, 344, 351, 358, 360, 440
]

EYES_SURFACE_INDICES = [
    7, 22, 23, 24, 33, 110, 130, 133, 144, 145, 153, 154, 155, 157, 158, 159, 160, 161,
    163, 173, 246, 247, 249, 263, 339, 341, 359, 362, 373, 374, 380, 381, 382, 384, 385,
    386, 387, 388, 390, 398, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477
]

EYEBROWS_SURFACE_INDICES = EYEBROWS_MESH_INDICES

MOUTH_SURFACE_INDICES = [
    0, 11, 12, 13, 14, 15, 16, 17, 37, 38, 39, 40, 41, 42, 61, 62, 72, 73, 74, 76, 77,
    78, 80, 81, 82, 84, 85, 86, 87, 88, 91, 95, 96, 146, 178, 179, 180, 181, 183, 184,
    185, 191, 267, 268, 269, 270, 271, 272, 291, 292, 302, 303, 304, 306, 307, 308,
    310, 311, 312, 314, 315, 316, 317, 318, 321, 324, 325, 375, 402, 403, 404, 405,
    407, 408, 409, 415
]

FACE_SHAPE_SURFACE_INDICES = [
    9, 10, 21, 50, 54, 58, 67, 69, 93, 101, 104, 108, 109, 116, 117, 118, 119, 120,
    123, 124, 127, 132, 136, 137, 138, 139, 147, 148, 149, 150, 151, 152, 162, 172,
    176, 177, 187, 192, 203, 205, 206, 207, 210, 211, 212, 213, 214, 215, 216, 227,
    228, 229, 230, 231, 232, 234, 280, 299, 323, 330, 333, 337, 338, 346, 347, 348,
    349, 350, 352, 355, 356, 357, 361, 363, 364, 365, 366, 367, 376, 377, 378, 379,
    389, 397, 400, 401, 411, 416, 423, 425, 426, 427, 430, 431, 432, 433, 434, 435,
    436, 454
]

SURFACE_PART_TO_INDICES = {
    "Nose": NOSE_SURFACE_INDICES,
    "Eyes": EYES_SURFACE_INDICES,
    "Eyebrows": EYEBROWS_SURFACE_INDICES,
    "Mouth": MOUTH_SURFACE_INDICES,
    "Face Shape": FACE_SHAPE_SURFACE_INDICES,
}

FULL_PART_TO_INDICES = {
    "Nose": NOSE_MESH_INDICES,
    "Eyes": EYES_MESH_INDICES,
    "Eyebrows": EYEBROWS_MESH_INDICES,
    "Mouth": LIPS_MESH_INDICES,
    "Face Shape": FACE_SHAPE_MESH_INDICES,
}

SURFACE_PART_PREFIXES = {
    "Nose": "Surface_Nose",
    "Eyes": "Surface_Eye_Area",
    "Eyebrows": "Surface_Eyebrow_Area",
    "Mouth": "Surface_Mouth_Area",
    "Face Shape": "Surface_Face_Shape",
}

TRACKER_DENSITY_LABELS = [
    "Sparse (Standard)",
    "Dense (Feature Contours)",
    "Full (Entire Mesh & Iris - 478 pts)",
]

PROFILE_ORDER = ("sparse", "dense", "full")
TRACKER_PART_ORDER = ("nose", "eyes", "eyebrows", "mouth", "face")
PART_LABELS = {
    "nose": "Nose",
    "eyes": "Eyes",
    "eyebrows": "Eyebrows",
    "mouth": "Mouth",
    "face": "Face",
}
PART_KNOB_NAMES = {
    "nose": "track_nose",
    "eyes": "track_eyes",
    "eyebrows": "track_eyebrows",
    "mouth": "track_mouth",
    "face": "track_contour",
}
PART_DEFAULTS = {
    "nose": True,
    "eyes": True,
    "eyebrows": False,
    "mouth": True,
    "face": True,
}
TOKEN_ALIASES = {
    "right_eyebrwo": "right_eyebrow",
    "let_alae": "left_ala",
    "left_alae": "left_ala",
    "right_alae": "right_ala",
    "symetry_axis": "symmetry_axis",
}

PROFILE_MAPPINGS = {}
PROFILE_LANDMARKS = {}
GRID_MAPPING = {}
GRID_LANDMARKS = {}
ACTIVE_MAPPING_PATH = DEFAULT_MAPPING_PATH


def _sanitize_token(value):
    token = re.sub(r"[^0-9A-Za-z]+", "_", str(value).strip().lower()).strip("_")
    token = TOKEN_ALIASES.get(token, token)
    return token or "unnamed"


def _display_label(value):
    return _sanitize_token(value).replace("_", " ").title()


def _normalize_part(value):
    token = _sanitize_token(value)
    if token == "face_shape":
        return "face"
    return token


def _density_key(density):
    value = str(density).lower()
    if "full" in value:
        return "full"
    if "dense" in value or "contour" in value:
        return "dense"
    if "surface" in value:
        # Surface was an older plugin-only density. The tool mapping now owns
        # sparse/dense/full, so keep Surface imports/export calls compatible by
        # resolving them to the closest authored profile.
        return "dense"
    return "sparse"


def _coerce_ids(value):
    if isinstance(value, dict):
        value = value.get("ids", [])
    if not isinstance(value, (list, tuple)):
        return []

    ids = []
    for item in value:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < 478:
            ids.append(idx)
    return ids


def _track_name(profile_name, parent_name, child_name, position=None, count=1):
    base = "{}_{}_{}".format(
        _sanitize_token(profile_name),
        _sanitize_token(parent_name),
        _sanitize_token(child_name),
    )
    if count == 1 or position is None:
        return base
    return "{}_{}".format(base, int(position))


def grid_track_name(row, col):
    return "grid_r{:02d}_c{:02d}".format(int(row) + 1, int(col) + 1)


def _roto_contour_name(parent_name, child_name):
    return _track_name("roto", parent_name, child_name)


def _iter_profile_children(profile_name):
    profile = PROFILE_MAPPINGS.get(profile_name, {})
    if not isinstance(profile, dict):
        return

    for parent_name, children in profile.items():
        if not isinstance(children, dict):
            continue
        parent_key = _normalize_part(parent_name)
        for child_name, value in children.items():
            child_key = _sanitize_token(child_name)
            child_parent_key = parent_key
            if "eyebrow" in child_key:
                child_parent_key = "eyebrows"
            yield child_parent_key, parent_name, child_name, value


def _build_regular_landmarks(profile_name):
    by_part = {}
    for parent_key, parent_name, child_name, value in _iter_profile_children(profile_name):
        ids = _coerce_ids(value)
        if not ids:
            continue
        part_landmarks = by_part.setdefault(parent_key, {})
        for position, idx in enumerate(ids):
            name = _track_name(profile_name, parent_name, child_name, position, len(ids))
            part_landmarks[name] = idx
    return by_part


def _build_roto_contours():
    contours = {}
    open_groups = set()
    knob_specs = []
    colors = {}

    for parent_key, parent_name, child_name, value in _iter_profile_children("roto"):
        ids = _coerce_ids(value)
        if not ids:
            continue

        contour_name = _roto_contour_name(parent_name, child_name)
        contours[contour_name] = ids
        if isinstance(value, dict) and value.get("openSpline"):
            open_groups.add(contour_name)

        if isinstance(value, dict) and value.get("color"):
            rgb = hex_to_rgb(value["color"])
            if rgb:
                colors[contour_name] = rgb

        knob_name = "roto_{}_{}".format(_sanitize_token(parent_name), _sanitize_token(child_name))
        label = "{} / {} ({} pts)".format(_display_label(parent_name), _display_label(child_name), len(ids))
        default_value = parent_key in ("face", "mouth", "eyes")
        knob_specs.append((knob_name, contour_name, label, default_value))

    return contours, tuple(open_groups), tuple(knob_specs), colors


def _build_grid_landmarks(grid_mapping):
    landmarks = {}
    if not isinstance(grid_mapping, dict):
        return landmarks

    for point in grid_mapping.get("points", []):
        if not isinstance(point, dict):
            continue
        if point.get("id") is None:
            continue
        try:
            row = int(point.get("row"))
            col = int(point.get("col"))
            idx = int(point.get("id"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < 478:
            landmarks[grid_track_name(row, col)] = idx
    return landmarks


def _load_mapping_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mapping JSON must contain an object.")

    profiles = data.get("profiles", data)
    if not isinstance(profiles, dict):
        raise ValueError("Mapping JSON must contain a 'profiles' object.")

    return profiles


def load_mapping(path=None):
    """Load mapping profiles from JSON and update the module-level API.

    The frontend can call this before analysis/export with a node-specific path.
    The backend calls it from CLI args. Existing callers keep using constants and
    resolver functions without needing to know where the mapping came from.
    """
    global ACTIVE_MAPPING_PATH, PROFILE_MAPPINGS, PROFILE_LANDMARKS
    global LANDMARK_GROUPS, SPARSE_PART_TO_LANDMARKS, DENSE_PART_TO_CONTOURS
    global CONTOUR_GROUPS, ROTO_CONTOUR_GROUP_NAMES, ROTO_CONTOUR_KNOB_SPECS
    global OPEN_CONTOUR_GROUPS, ALL_LANDMARKS, INDEX_TO_NAME
    global GRID_MAPPING, GRID_LANDMARKS, TRACKER_DENSITY_LABELS
    global ROTO_CONTOUR_COLORS

    resolved_path = path or DEFAULT_MAPPING_PATH
    resolved_path = os.path.abspath(os.path.expanduser(resolved_path))
    profiles = _load_mapping_json(resolved_path)

    PROFILE_MAPPINGS = {
        "sparse": profiles.get("sparse", {}),
        "dense": profiles.get("dense", {}),
        "full": profiles.get("full", {}),
        "roto": profiles.get("roto", {}),
        "grid": profiles.get("grid", {}),
    }
    PROFILE_LANDMARKS = {
        profile_name: _build_regular_landmarks(profile_name)
        for profile_name in PROFILE_ORDER
    }

    LANDMARK_GROUPS = PROFILE_LANDMARKS.get("sparse", {})
    SPARSE_PART_TO_LANDMARKS = LANDMARK_GROUPS
    CONTOUR_GROUPS, OPEN_CONTOUR_GROUPS, ROTO_CONTOUR_KNOB_SPECS, ROTO_CONTOUR_COLORS = _build_roto_contours()
    ROTO_CONTOUR_GROUP_NAMES = tuple(CONTOUR_GROUPS.keys())
    DENSE_PART_TO_CONTOURS = {}

    GRID_MAPPING = PROFILE_MAPPINGS.get("grid", {})
    GRID_LANDMARKS = _build_grid_landmarks(GRID_MAPPING)

    ALL_LANDMARKS = {}
    for profile_landmarks in PROFILE_LANDMARKS.values():
        for landmarks in profile_landmarks.values():
            ALL_LANDMARKS.update(landmarks)
    ALL_LANDMARKS.update(GRID_LANDMARKS)
    INDEX_TO_NAME = {idx: name for name, idx in ALL_LANDMARKS.items()}

    TRACKER_DENSITY_LABELS = ["Sparse", "Dense", "Full"]
    ACTIVE_MAPPING_PATH = resolved_path
    return PROFILE_MAPPINGS


def get_active_mapping_path():
    return ACTIVE_MAPPING_PATH


def get_tracker_part_specs():
    available = set()
    for profile_name in PROFILE_ORDER:
        available.update(PROFILE_LANDMARKS.get(profile_name, {}).keys())

    ordered = [part for part in TRACKER_PART_ORDER if part in available]
    ordered.extend(sorted(part for part in available if part not in ordered))

    return [
        (
            PART_KNOB_NAMES.get(part, "track_{}".format(part)),
            part,
            PART_LABELS.get(part, _display_label(part)),
            PART_DEFAULTS.get(part, True),
        )
        for part in ordered
    ]


def get_grid_mapping():
    return GRID_MAPPING


def get_grid_landmarks():
    return dict(GRID_LANDMARKS)


def get_roto_contour_names():
    return list(ROTO_CONTOUR_GROUP_NAMES)


def _add_indexed_landmarks(resolved, prefix, indices):
    for i, idx in enumerate(indices):
        resolved[f"{prefix}_{i}"] = idx


def _merge_landmarks(target, source):
    for name, idx in source.items():
        target[name] = idx


SURFACE_LANDMARKS = {}
for part_name, indices in SURFACE_PART_TO_INDICES.items():
    _add_indexed_landmarks(SURFACE_LANDMARKS, SURFACE_PART_PREFIXES[part_name], indices)


# --- DYNAMIC LANDMARK RESOLVER ---
def get_landmarks_for_density(density, active_parts):
    """
    Returns a resolved dictionary of {landmark_name: index} based on density level
    and list of active parts selected by the user.
    """
    resolved = {}
    density_key = _density_key(density)
    profile_landmarks = PROFILE_LANDMARKS.get(density_key, {})
    active_set = {_normalize_part(part) for part in active_parts}

    for part, landmarks in profile_landmarks.items():
        if part in active_set:
            resolved.update(landmarks)

    return resolved


def get_all_part_names():
    return [part for _knob_name, part, _label, _default in get_tracker_part_specs()]


def get_landmarks_for_analysis():
    """
    Returns the full export superset of tracker landmarks recorded during analysis.

    No filtering is applied: every density and every part is merged into a single
    resolved dictionary. Tracker and Roto exports filter this superset later
    according to the user's current frontend choices.
    """
    resolved = {}
    parts = get_all_part_names()

    for analysis_density in ("Sparse", "Dense", "Full"):
        _merge_landmarks(resolved, get_landmarks_for_density(analysis_density, parts))
    _merge_landmarks(resolved, GRID_LANDMARKS)

    return resolved


def resolve_contour_point(name):
    """
    Resolve a contour point track name to its contour group and in-group position.

    Contour point names follow the ``GroupName_N`` convention (e.g. ``Face_Oval_3``),
    where ``N`` is the 0-based position within that group's point list in
    ``CONTOUR_GROUPS`` (NOT the MediaPipe landmark index).

    Returns ``(group_name, N)`` when ``name`` matches a contour group prefix and
    ``N`` is in range for that group, otherwise ``None``.
    """
    for group_name, indices in CONTOUR_GROUPS.items():
        prefix = group_name + "_"
        if name.startswith(prefix):
            try:
                idx_in_group = int(name[len(prefix):])
            except ValueError:
                return None
            if 0 <= idx_in_group < len(indices):
                return (group_name, idx_in_group)
            return None
    return None


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


load_mapping(DEFAULT_MAPPING_PATH)
