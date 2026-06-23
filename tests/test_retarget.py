import os
import sys
import unittest
import math
from unittest.mock import MagicMock

# Ensure project root (which contains backend/ and frontend/) is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also ensure frontend and backend are directly importable for direct imports
sys.path.insert(0, os.path.join(project_root, "backend"))
sys.path.insert(0, os.path.join(project_root, "frontend"))

# Mock nuke module before importing nuke_tracker
if 'nuke' not in sys.modules:
    sys.modules['nuke'] = MagicMock()

import backend.retarget as retarget
import nuke_tracker


class TestExpressionRetargeting(unittest.TestCase):

    def setUp(self):
        # Build a standard resting 90-point reference grid for testing
        # Row 0 to 9, Col 0 to 8
        self.grid_points_ref = []
        for r in range(10):
            for c in range(9):
                self.grid_points_ref.append({
                    "row": r,
                    "col": c,
                    "id": r * 9 + c,
                    "x": float(c * 2.0),
                    "y": float(r * 2.0)
                })
        
        self.canonical_interocular = retarget.get_canonical_interocular()

    def test_canonical_interocular_calculation(self):
        """3.3: Verify that get_canonical_interocular returns the correct reference distance (~5.657117)."""
        val = retarget.get_canonical_interocular()
        self.assertAlmostEqual(val, 5.657117, places=4)

    def test_retarget_compute_destination_grid(self):
        """3.3: Verify compute_destination_grid works and jawOpen pulls the chin downwards (decreasing Y)."""
        # Define jawOpen blendshape values on frame '1'
        blendshape_frames = {
            "1": {"jawOpen": 0.5}
        }
        
        global_intensity = 1.0
        zone_intensities = {
            "brows": 1.0,
            "eyes": 1.0,
            "mouth": 1.0,
            "other": 1.0
        }
        
        res = retarget.compute_destination_grid(
            grid_points_ref=self.grid_points_ref,
            blendshape_frames=blendshape_frames,
            global_intensity=global_intensity,
            zone_intensities=zone_intensities
        )
        
        self.assertIn("1", res)
        frame_points = res["1"]
        self.assertEqual(len(frame_points), 90)
        
        # Point at Row 9, Col 4 (index 85) is the chin, which jawOpen pulls down.
        pt_rest = next(p for p in self.grid_points_ref if p["row"] == 9 and p["col"] == 4)
        pt_anim = next(p for p in frame_points if p["row"] == 9 and p["col"] == 4)
        
        # Check that it pulled down (decreasing Y in our Nuke-aligned delta space)
        # Delta for jawOpen at row 9, col 4 is -1.2 (from BLENDSHAPE_DELTAS_2D)
        # Expected dy = 0.5 (blendshape score) * 1.0 (global) * 1.0 (zone) * -1.2 = -0.6
        # Real interocular in synthetic grid is 8.0 (from x=4.0 to x=12.0)
        # S = 8.0 / self.canonical_interocular
        # Scaled dy = -0.6 * S
        # Expected anim Y = 18.0 + Scaled dy
        scale = 8.0 / self.canonical_interocular
        expected_dy = -0.6 * scale
        expected_y = 18.0 + expected_dy
        
        self.assertAlmostEqual(pt_anim["x"], pt_rest["x"], places=5)
        self.assertAlmostEqual(pt_anim["y"], expected_y, places=5)
        
        # Verify a point with no jawOpen deltas (e.g., Row 0, Col 0) remains unchanged
        pt_rest_unaffected = next(p for p in self.grid_points_ref if p["row"] == 0 and p["col"] == 0)
        pt_anim_unaffected = next(p for p in frame_points if p["row"] == 0 and p["col"] == 0)
        self.assertEqual(pt_anim_unaffected["x"], pt_rest_unaffected["x"])
        self.assertEqual(pt_anim_unaffected["y"], pt_rest_unaffected["y"])

    def test_retarget_zone_intensity(self):
        """3.3: Verify zone intensity sliders correctly mute or amplify specific zones."""
        # Use mouthSmileLeft (mouth zone) and browInnerUp (brows zone)
        blendshape_frames = {
            "1": {
                "mouthSmileLeft": 1.0,
                "browInnerUp": 1.0
            }
        }
        
        # Case A: Brows zone is muted (0.0), Mouth zone is full (1.0)
        res_brows_muted = retarget.compute_destination_grid(
            grid_points_ref=self.grid_points_ref,
            blendshape_frames=blendshape_frames,
            global_intensity=1.0,
            zone_intensities={
                "brows": 0.0,
                "eyes": 1.0,
                "mouth": 1.0,
                "other": 1.0
            }
        )
        
        # Check brow point (e.g., Row 1, Col 4 - browInnerUp)
        pt_brow_rest = next(p for p in self.grid_points_ref if p["row"] == 1 and p["col"] == 4)
        pt_brow_muted = next(p for p in res_brows_muted["1"] if p["row"] == 1 and p["col"] == 4)
        # Brows are muted, so Y should be unchanged
        self.assertEqual(pt_brow_muted["y"], pt_brow_rest["y"])
        
        # Check mouth point (e.g., Row 8, Col 6 - mouthSmileLeft)
        pt_mouth_rest = next(p for p in self.grid_points_ref if p["row"] == 8 and p["col"] == 6)
        pt_mouth_muted = next(p for p in res_brows_muted["1"] if p["row"] == 8 and p["col"] == 6)
        # Mouth is active, so Y should have changed (moved up/out)
        self.assertNotEqual(pt_mouth_muted["y"], pt_mouth_rest["y"])
        
        # Case B: Brows zone is full (1.0), Mouth zone is muted (0.0)
        res_mouth_muted = retarget.compute_destination_grid(
            grid_points_ref=self.grid_points_ref,
            blendshape_frames=blendshape_frames,
            global_intensity=1.0,
            zone_intensities={
                "brows": 1.0,
                "eyes": 1.0,
                "mouth": 0.0,
                "other": 1.0
            }
        )
        
        pt_brow_active = next(p for p in res_mouth_muted["1"] if p["row"] == 1 and p["col"] == 4)
        pt_mouth_muted2 = next(p for p in res_mouth_muted["1"] if p["row"] == 8 and p["col"] == 6)
        
        # Brow should now be altered
        self.assertNotEqual(pt_brow_active["y"], pt_brow_rest["y"])
        # Mouth should be unchanged
        self.assertEqual(pt_mouth_muted2["y"], pt_mouth_rest["y"])

    def test_retarget_scale_and_rotation(self):
        """3.3: Verify scale (S) and rotation (theta) compensation math works perfectly."""
        # 1. Scale test: interocular distance of 2x canonical -> scale should be 2.0
        scale_factor = 2.0
        ref_distance = self.canonical_interocular * scale_factor
        
        # Create eye-aligned points with exactly ref_distance separation, no rotation
        grid_points_scale = []
        for r in range(10):
            for c in range(9):
                # Align eye points at row 2 col 2 & col 6
                # Row 2, Col 2: (0, 0)
                # Row 2, Col 6: (ref_distance, 0)
                # To make interocular distance exactly ref_distance:
                # separation between col 2 and col 6 is 4 columns.
                # So we can set X = c * (ref_distance / 4.0)
                grid_points_scale.append({
                    "row": r,
                    "col": c,
                    "id": r * 9 + c,
                    "x": float(c * (ref_distance / 4.0)),
                    "y": float(r * 2.0)
                })
                
        # browInnerUp at row 1, col 4 has delta (0.0, 0.8)
        blendshape_frames = {"1": {"browInnerUp": 1.0}}
        
        res = retarget.compute_destination_grid(
            grid_points_ref=grid_points_scale,
            blendshape_frames=blendshape_frames,
            global_intensity=1.0,
            zone_intensities={"brows": 1.0, "eyes": 1.0, "mouth": 1.0, "other": 1.0}
        )
        
        pt_brow_rest = next(p for p in grid_points_scale if p["row"] == 1 and p["col"] == 4)
        pt_brow_anim = next(p for p in res["1"] if p["row"] == 1 and p["col"] == 4)
        
        # Expected displacement = canonical_delta * global_intensity * zone_intensity * scale
        # Expected displacement = (0.0, 0.8) * 1.0 * 1.0 * 2.0 = (0.0, 1.6)
        # Check if dy is exactly 1.6
        self.assertAlmostEqual(pt_brow_anim["y"] - pt_brow_rest["y"], 1.6, places=5)
        
        # 2. Rotation test: Rotate eye points by 90 degrees (theta = pi/2)
        # Let's construct a grid where the right eye is directly above the left eye
        # Row 2 Col 2 is at (0, 0)
        # Row 2 Col 6 is at (0, canonical_interocular) -> theta = pi/2 (90 deg CCW/CW depending on coordinates)
        # Distance = canonical_interocular -> Scale S = 1.0
        grid_points_rot = []
        for r in range(10):
            for c in range(9):
                # Separation is 4 columns. Set base step to canonical_interocular / 4.0
                step = self.canonical_interocular / 4.0
                # Rotated by 90 degrees: x becomes vertical, y becomes horizontal
                # dx = 0, dy = separation -> col 6 is above col 2
                grid_points_rot.append({
                    "row": r,
                    "col": c,
                    "id": r * 9 + c,
                    "x": 0.0,
                    "y": float(c * step)
                })
                
        # browInnerUp at row 1, col 4 has delta (dx=0.0, dy=0.8)
        # Under theta = pi/2, a delta of (dx=0.0, dy=0.8) should rotate to:
        # rot_dx = dx * cos(pi/2) - dy * sin(pi/2) = 0 - 0.8 * 1 = -0.8
        # rot_dy = dx * sin(pi/2) + dy * cos(pi/2) = 0 + 0 = 0.0
        # So we expect dy displacement to be 0.0 and dx displacement to be -0.8!
        res_rot = retarget.compute_destination_grid(
            grid_points_ref=grid_points_rot,
            blendshape_frames=blendshape_frames,
            global_intensity=1.0,
            zone_intensities={"brows": 1.0, "eyes": 1.0, "mouth": 1.0, "other": 1.0}
        )
        
        pt_brow_rot_rest = next(p for p in grid_points_rot if p["row"] == 1 and p["col"] == 4)
        pt_brow_rot_anim = next(p for p in res_rot["1"] if p["row"] == 1 and p["col"] == 4)
        
        self.assertAlmostEqual(pt_brow_rot_anim["x"] - pt_brow_rot_rest["x"], -0.8, places=5)
        self.assertAlmostEqual(pt_brow_rot_anim["y"] - pt_brow_rot_rest["y"], 0.0, places=5)

    def test_blink_filter_logic(self):
        """3.3: Verify apply_blink_filter freezes eye/eyelid coordinates during eyeBlink > 0.5."""
        # Create animated dest frames for 3 frames:
        # Frame 1: Resting eye points
        # Frame 2: Left eyelid moved significantly, eyeBlinkLeft = 1.0
        # Frame 3: Eye open again, blink score = 0.0
        
        left_eye_pt_ref = next(p for p in self.grid_points_ref if p["row"] == 2 and p["col"] == 6)
        
        animated_dest_frames = {
            "1": [dict(p) for p in self.grid_points_ref],
            "2": [dict(p) for p in self.grid_points_ref],
            "3": [dict(p) for p in self.grid_points_ref]
        }
        
        # Modify Left Eye points in Frame 2 to simulate movement
        for pt in animated_dest_frames["2"]:
            if pt["row"] == 2 and pt["col"] == 6:
                pt["x"] += 5.0
                pt["y"] += 5.0
                
        # Modify Left Eye points in Frame 3 to simulate new movement
        for pt in animated_dest_frames["3"]:
            if pt["row"] == 2 and pt["col"] == 6:
                pt["x"] += 10.0
                pt["y"] += 10.0
                
        # Eyelid blendshapes
        blendshape_frames = {
            "1": {"eyeBlinkLeft": 0.0},
            "2": {"eyeBlinkLeft": 1.0}, # BLINKING Left
            "3": {"eyeBlinkLeft": 0.0}  # Recovered
        }
        
        filtered = nuke_tracker.apply_blink_filter(animated_dest_frames, blendshape_frames)
        
        # Frame 1: Should be identical to original Frame 1
        pt_f1 = next(p for p in filtered["1"] if p["row"] == 2 and p["col"] == 6)
        self.assertEqual(pt_f1["x"], left_eye_pt_ref["x"])
        self.assertEqual(pt_f1["y"], left_eye_pt_ref["y"])
        
        # Frame 2: Blinking, so it should be FROZEN to Frame 1's value (last non-blinking frame)
        pt_f2 = next(p for p in filtered["2"] if p["row"] == 2 and p["col"] == 6)
        self.assertEqual(pt_f2["x"], left_eye_pt_ref["x"])
        self.assertEqual(pt_f2["y"], left_eye_pt_ref["y"])
        
        # Frame 3: Blink is over, so it should RECOVER to its animated Frame 3 position
        pt_f3 = next(p for p in filtered["3"] if p["row"] == 2 and p["col"] == 6)
        self.assertEqual(pt_f3["x"], left_eye_pt_ref["x"] + 10.0)
        self.assertEqual(pt_f3["y"], left_eye_pt_ref["y"] + 10.0)


if __name__ == "__main__":
    unittest.main()
