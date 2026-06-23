"""
Expression Retargeting Engine (2D) for NukeFaceTracker.

This module provides the core 2D facial motion retargeting calculations,
mapping ARKit blendshapes to displacements for a 90-point GridWarp3 grid.
"""
import math
from typing import Dict, List, Tuple, Any

from backend.blendshapes_config import ARKIT_BLENDSHAPE_NAMES, BLENDSHAPE_ZONES
from backend.landmarks_config import GRID_MAPPING

def _generate_blendshape_deltas_2d() -> Dict[str, List[Tuple[float, float]]]:
    """
    Generate 2D displacement vectors (dx, dy) in head-aligned space
    for each of the 52 ARKit blendshapes for all 90 grid points.
    
    Coordinates orientation:
      - dx > 0: moves right
      - dx < 0: moves left
      - dy > 0: moves up
      - dy < 0: moves down
    """
    deltas = {}
    for name in ARKIT_BLENDSHAPE_NAMES:
        deltas[name] = [(0.0, 0.0) for _ in range(90)]
        
    def set_delta(bs_name: str, r: int, c: int, dx: float, dy: float):
        idx = r * 9 + c
        if 0 <= idx < 90:
            deltas[bs_name][idx] = (float(dx), float(dy))

    # --- BROWS (Rows 1-2) ---
    # browInnerUp: Inner brows move up. Row 1-2, Cols 3-5.
    for col, weight in [(3, 0.5), (4, 1.0), (5, 0.5)]:
        set_delta("browInnerUp", 1, col, 0.0, weight * 0.8)
        set_delta("browInnerUp", 2, col, 0.0, weight * 0.4)
        
    # browDownLeft: Left brow (viewer's right, cols 5-8) moves down.
    for col, weight in [(5, 0.3), (6, 0.8), (7, 1.0), (8, 0.5)]:
        set_delta("browDownLeft", 1, col, 0.0, -weight * 0.7)
        set_delta("browDownLeft", 2, col, 0.0, -weight * 0.3)
        
    # browDownRight: Right brow (viewer's left, cols 0-3) moves down.
    for col, weight in [(0, 0.5), (1, 1.0), (2, 0.8), (3, 0.3)]:
        set_delta("browDownRight", 1, col, 0.0, -weight * 0.7)
        set_delta("browDownRight", 2, col, 0.0, -weight * 0.3)

    # browOuterUpLeft: Left outer brow (cols 6-8) moves up.
    for col, weight in [(6, 0.4), (7, 0.9), (8, 0.6)]:
        set_delta("browOuterUpLeft", 1, col, 0.0, weight * 0.7)
        set_delta("browOuterUpLeft", 2, col, 0.0, weight * 0.3)
        
    # browOuterUpRight: Right outer brow (cols 0-2) moves up.
    for col, weight in [(0, 0.6), (1, 0.9), (2, 0.4)]:
        set_delta("browOuterUpRight", 1, col, 0.0, weight * 0.7)
        set_delta("browOuterUpRight", 2, col, 0.0, weight * 0.3)

    # --- EYES (Rows 2-3) ---
    # eyeBlinkLeft: Left eye (viewer's right, Row 2-3, Cols 5-7) closes.
    for col, weight in [(5, 0.5), (6, 1.0), (7, 0.5)]:
        set_delta("eyeBlinkLeft", 2, col, 0.0, -weight * 0.8)
        set_delta("eyeBlinkLeft", 3, col, 0.0, weight * 0.3)
        
    # eyeBlinkRight: Right eye (viewer's left, Row 2-3, Cols 1-3) closes.
    for col, weight in [(1, 0.5), (2, 1.0), (3, 0.5)]:
        set_delta("eyeBlinkRight", 2, col, 0.0, -weight * 0.8)
        set_delta("eyeBlinkRight", 3, col, 0.0, weight * 0.3)

    # eyeSquintLeft / Right: eyelid narrows.
    for col, weight in [(5, 0.4), (6, 0.7), (7, 0.4)]:
        set_delta("eyeSquintLeft", 2, col, 0.0, -weight * 0.3)
        set_delta("eyeSquintLeft", 3, col, 0.0, weight * 0.3)
    for col, weight in [(1, 0.4), (2, 0.7), (3, 0.4)]:
        set_delta("eyeSquintRight", 2, col, 0.0, -weight * 0.3)
        set_delta("eyeSquintRight", 3, col, 0.0, weight * 0.3)

    # eyeWideLeft / Right: eyelid opens.
    for col, weight in [(5, 0.5), (6, 1.0), (7, 0.5)]:
        set_delta("eyeWideLeft", 2, col, 0.0, weight * 0.6)
        set_delta("eyeWideLeft", 3, col, 0.0, -weight * 0.3)
    for col, weight in [(1, 0.5), (2, 1.0), (3, 0.5)]:
        set_delta("eyeWideRight", 2, col, 0.0, weight * 0.6)
        set_delta("eyeWideRight", 3, col, 0.0, -weight * 0.3)

    # --- MOUTH (Rows 7-8) ---
    # mouthSmileLeft: Left mouth corner (Row 8, Col 6) moves up and out.
    set_delta("mouthSmileLeft", 8, 6, 0.8, 0.8)
    set_delta("mouthSmileLeft", 8, 5, 0.4, 0.4)
    set_delta("mouthSmileLeft", 7, 6, 0.4, 0.4)
    set_delta("mouthSmileLeft", 9, 6, 0.4, 0.2)
    
    # mouthSmileRight: Right mouth corner (Row 8, Col 2) moves up and out.
    set_delta("mouthSmileRight", 8, 2, -0.8, 0.8)
    set_delta("mouthSmileRight", 8, 3, -0.4, 0.4)
    set_delta("mouthSmileRight", 7, 2, -0.4, 0.4)
    set_delta("mouthSmileRight", 9, 2, -0.4, 0.2)

    # mouthFrownLeft: Left corner moves down and slightly out.
    set_delta("mouthFrownLeft", 8, 6, 0.2, -0.6)
    set_delta("mouthFrownLeft", 8, 5, 0.1, -0.3)
    set_delta("mouthFrownLeft", 9, 6, 0.1, -0.3)

    # mouthFrownRight: Right corner moves down and slightly out.
    set_delta("mouthFrownRight", 8, 2, -0.2, -0.6)
    set_delta("mouthFrownRight", 8, 3, -0.1, -0.3)
    set_delta("mouthFrownRight", 9, 2, -0.1, -0.3)

    # mouthPucker: mouth narrows (dx towards center Col 4)
    for row in (7, 8):
        for col, weight in [(2, 0.6), (3, 0.8), (4, 0.0), (5, -0.8), (6, -0.6)]:
            set_delta("mouthPucker", row, col, weight * 0.6, 0.0)

    # mouthFunnel: mouth opens in 'O' shape (dx outwards, dy opens lips)
    for col, weight in [(2, -0.3), (3, -0.1), (4, 0.0), (5, 0.1), (6, 0.3)]:
        set_delta("mouthFunnel", 7, col, weight * 0.5, 0.5)
        set_delta("mouthFunnel", 8, col, weight * 0.5, -0.5)

    # mouthUpperUpLeft:
    set_delta("mouthUpperUpLeft", 7, 5, 0.0, 0.6)
    set_delta("mouthUpperUpLeft", 7, 6, 0.0, 0.4)
    
    # mouthUpperUpRight:
    set_delta("mouthUpperUpRight", 7, 3, 0.0, 0.6)
    set_delta("mouthUpperUpRight", 7, 2, 0.0, 0.4)

    # mouthLowerDownLeft:
    set_delta("mouthLowerDownLeft", 8, 5, 0.0, -0.6)
    set_delta("mouthLowerDownLeft", 8, 6, 0.0, -0.4)

    # mouthLowerDownRight:
    set_delta("mouthLowerDownRight", 8, 3, 0.0, -0.6)
    set_delta("mouthLowerDownRight", 8, 2, 0.0, -0.4)

    # --- JAW & OTHER (Row 9) ---
    # jawOpen: pulls lower lip (Row 8) and chin (Row 9) down
    for col, weight in [(3, 0.7), (4, 1.0), (5, 0.7)]:
        set_delta("jawOpen", 8, col, 0.0, -weight * 0.5)
        set_delta("jawOpen", 9, col, 0.0, -weight * 1.2)
    for col, weight in [(2, 0.4), (6, 0.4)]:
        set_delta("jawOpen", 8, col, 0.0, -weight * 0.3)
        set_delta("jawOpen", 9, col, 0.0, -weight * 0.8)
    for col, weight in [(1, 0.2), (7, 0.2)]:
        set_delta("jawOpen", 9, col, 0.0, -weight * 0.5)

    # jawLeft: pulls chin left
    for col in range(2, 7):
        set_delta("jawLeft", 9, col, -0.8, 0.0)
        set_delta("jawLeft", 8, col, -0.4, 0.0)

    # jawRight: pulls chin right
    for col in range(2, 7):
        set_delta("jawRight", 9, col, 0.8, 0.0)
        set_delta("jawRight", 8, col, 0.4, 0.0)

    # cheekPuff: blow cheeks out
    for row in (5, 6, 7):
        for col, weight in [(0, -0.8), (1, -0.6), (2, -0.3)]:
            set_delta("cheekPuff", row, col, weight, 0.0)
        for col, weight in [(6, 0.3), (7, 0.6), (8, 0.8)]:
            set_delta("cheekPuff", row, col, weight, 0.0)

    return deltas

# Statically cached deltas map
BLENDSHAPE_DELTAS_2D: Dict[str, List[Tuple[float, float]]] = _generate_blendshape_deltas_2d()

def get_canonical_interocular() -> float:
    """Returns the distance between eyes in the canonical 90-point grid mapping."""
    canonical_points = GRID_MAPPING.get("points", [])
    pt_r03_c03 = next((p for p in canonical_points if p["row"] == 2 and p["col"] == 2), None)
    pt_r03_c07 = next((p for p in canonical_points if p["row"] == 2 and p["col"] == 6), None)
    if pt_r03_c03 and pt_r03_c07:
        return math.sqrt((pt_r03_c07["x"] - pt_r03_c03["x"])**2 + (pt_r03_c07["y"] - pt_r03_c03["y"])**2)
    return 5.656854

def compute_destination_grid(
    grid_points_ref: List[Dict[str, Any]],
    blendshape_frames: Dict[str, Dict[str, float]],
    global_intensity: float,
    zone_intensities: Dict[str, float]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes the animated destination grid points for each frame by applying 
    the retargeted and compensated blendshape deltas to the reference grid.
    
    Args:
        grid_points_ref: The 90 reference points from the source tracked grid.
        blendshape_frames: A dictionary mapping frame numbers (as strings) to 
                           blendshape weights (e.g., {'1': {'jawOpen': 0.5, ...}}).
        global_intensity: Global multiplier for expression strength.
        zone_intensities: Multipliers for each logical zone ('brows', 'eyes', 'mouth', 'other').
        
    Returns:
        A dictionary mapping frame numbers (as strings) to list of computed points.
    """
    # 1. Identify eye points in the reference frame
    p_ref_c03 = next((p for p in grid_points_ref if p["row"] == 2 and p["col"] == 2), None)
    p_ref_c07 = next((p for p in grid_points_ref if p["row"] == 2 and p["col"] == 6), None)
    
    # 2. Compute Scale & Roll Compensation parameters from the reference frame
    canonical_interocular = get_canonical_interocular()
    if p_ref_c03 and p_ref_c07:
        dx = p_ref_c07["x"] - p_ref_c03["x"]
        dy = p_ref_c07["y"] - p_ref_c03["y"]
        source_interocular = math.sqrt(dx**2 + dy**2)
        theta = math.atan2(dy, dx)
        scale = source_interocular / canonical_interocular
    else:
        scale = 1.0
        theta = 0.0
        
    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)
    
    # Sort points by row then col to match the 1D BLENDSHAPE_DELTAS_2D indexing
    sorted_ref_points = sorted(grid_points_ref, key=lambda p: (p["row"], p["col"]))
    
    animated_dest_frames = {}
    for frame_key, scores in blendshape_frames.items():
        frame_points = []
        for point_idx, ref_pt in enumerate(sorted_ref_points):
            # 3. Accumulate deltas across all active blendshapes
            total_dx = 0.0
            total_dy = 0.0
            for bs_name, score in scores.items():
                if bs_name not in BLENDSHAPE_DELTAS_2D:
                    continue
                
                zone = BLENDSHAPE_ZONES.get(bs_name, "other")
                zone_intensity = zone_intensities.get(zone, 1.0)
                
                pt_dx, pt_dy = BLENDSHAPE_DELTAS_2D[bs_name][point_idx]
                
                total_dx += score * global_intensity * zone_intensity * pt_dx
                total_dy += score * global_intensity * zone_intensity * pt_dy
                
            # 4. Rotate and scale the accumulated delta vector
            rot_dx = total_dx * cos_theta - total_dy * sin_theta
            rot_dy = total_dx * sin_theta + total_dy * cos_theta
            
            scaled_dx = rot_dx * scale
            scaled_dy = rot_dy * scale
            
            # 5. Apply to neutral reference position
            frame_points.append({
                "row": ref_pt["row"],
                "col": ref_pt["col"],
                "id": ref_pt.get("id"),
                "x": ref_pt["x"] + scaled_dx,
                "y": ref_pt["y"] + scaled_dy
            })
            
        animated_dest_frames[frame_key] = frame_points
        
    return animated_dest_frames
