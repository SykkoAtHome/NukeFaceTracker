import os
import sys
import unittest

# Add backend to path so we can import modules
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import landmarks_config
import tracker_backend

class TestNukeFaceTracker(unittest.TestCase):

    def test_get_landmarks_by_names_all(self):
        """Test retrieving all landmarks when no names are specified."""
        res = landmarks_config.get_landmarks_by_names([])
        self.assertEqual(len(res), len(landmarks_config.ALL_LANDMARKS))
        self.assertIn("sparse_nose_tip", res)
        self.assertEqual(res["sparse_nose_tip"], 4)

    def test_get_landmarks_by_names_specific(self):
        """Test retrieving specific landmarks by their names."""
        names = ["sparse_nose_tip", "dense_eyes_left_eye_0"]
        res = landmarks_config.get_landmarks_by_names(names)
        self.assertEqual(len(res), 2)
        self.assertEqual(res["sparse_nose_tip"], 4)
        self.assertEqual(res["dense_eyes_left_eye_0"], 33)

    def test_get_landmarks_by_names_mesh_and_contour(self):
        """Test dynamic mesh and contour landmarks name resolution."""
        names = ["Mesh_152", "roto_mouth_lip_upper_1", "Invalid_Name", "Mesh_500", "roto_mouth_lip_upper_99"]
        res = landmarks_config.get_landmarks_by_names(names)
        self.assertEqual(len(res), 2)
        self.assertEqual(res["Mesh_152"], 152)
        self.assertEqual(res["roto_mouth_lip_upper_1"], 267)

    def test_get_landmarks_by_names_grid(self):
        """Test grid landmark name resolution."""
        res = landmarks_config.get_landmarks_by_names(["grid_r01_c01", "grid_r10_c09"])
        self.assertEqual(res["grid_r01_c01"], 54)
        self.assertEqual(res["grid_r10_c09"], 365)

    def test_get_contour_groups_by_names_all(self):
        """Test retrieving all contour groups when no names are specified."""
        res = landmarks_config.get_contour_groups_by_names([])
        self.assertEqual(len(res), len(landmarks_config.CONTOUR_GROUPS))
        self.assertIn("roto_face_chin", res)
        self.assertIn("roto_mouth_lip_upper", res)

    def test_get_contour_groups_by_names_specific(self):
        """Test retrieving specific contour groups by name."""
        names = ["roto_mouth_lip_upper", "roto_eyes_left_eye"]
        res = landmarks_config.get_contour_groups_by_names(names)
        self.assertEqual(len(res), 2)
        self.assertEqual(res["roto_mouth_lip_upper"], landmarks_config.CONTOUR_GROUPS["roto_mouth_lip_upper"])
        self.assertEqual(res["roto_eyes_left_eye"], landmarks_config.CONTOUR_GROUPS["roto_eyes_left_eye"])

    def test_get_frame_path_hash_pattern(self):
        """Test converting Nuke-style hash patterns (e.g. ####) to frame file path."""
        pattern = "D:/footage/shot_01/shot_01.####.png"
        path = tracker_backend.get_frame_path(pattern, 12)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.0012.png")

    def test_get_frame_path_custom_hash_pattern(self):
        """Test converting Nuke-style custom hash patterns (e.g. ###) to frame file path."""
        pattern = "D:/footage/shot_01/shot_01.###.png"
        path = tracker_backend.get_frame_path(pattern, 5)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.005.png")

    def test_get_frame_path_printf_pattern(self):
        """Test converting standard printf patterns (e.g. %04d) to frame file path."""
        pattern = "D:/footage/shot_01/shot_01.%04d.png"
        path = tracker_backend.get_frame_path(pattern, 101)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.0101.png")

    def test_get_frame_path_static(self):
        """Test get_frame_path with a static image path (no patterns)."""
        pattern = "D:/footage/shot_01/reference_frame.png"
        path = tracker_backend.get_frame_path(pattern, 10)
        self.assertEqual(path, "D:/footage/shot_01/reference_frame.png")

    def test_nose_alar_orientations(self):
        """Verify person's left is 358 (screen right) and person's right is 129 (screen left)."""
        self.assertEqual(landmarks_config.LANDMARK_GROUPS["nose"]["sparse_nose_right_ala"], 358)
        self.assertEqual(landmarks_config.LANDMARK_GROUPS["nose"]["sparse_nose_left_ala"], 129)

    def test_nose_bridge_scalar_and_contour_do_not_collide(self):
        """Verify sparse Nose_Bridge and dense nose bridge contour use distinct JSON keys."""
        self.assertEqual(landmarks_config.LANDMARK_GROUPS["nose"]["sparse_nose_bridge"], 168)
        self.assertNotIn("sparse_nose_bridge", landmarks_config.CONTOUR_GROUPS)
        self.assertIn("roto_nose_bridge", landmarks_config.CONTOUR_GROUPS)

        res = landmarks_config.get_landmarks_for_density("Dense (Contours - 149 pts)", ["Nose"])
        self.assertEqual(res["dense_nose_bridge_0"], 168)
        self.assertEqual(res["dense_nose_bridge_1"], 197)

    def test_mesh_partition_properties(self):
        """Verify that the 478 landmark mesh is partitioned cleanly with no overlaps or missing indices."""
        eyebrows = set(landmarks_config.EYEBROWS_MESH_INDICES)
        eyes = set(landmarks_config.EYES_MESH_INDICES)
        lips = set(landmarks_config.LIPS_MESH_INDICES)
        nose = set(landmarks_config.NOSE_MESH_INDICES)
        face_shape = set(landmarks_config.FACE_SHAPE_MESH_INDICES)

        # Check total number of points across partitions
        sum_lengths = len(eyebrows) + len(eyes) + len(lips) + len(nose) + len(face_shape)
        self.assertEqual(sum_lengths, 478)

        # Check union contains all 478 indices with no gaps
        union_set = eyebrows | eyes | lips | nose | face_shape
        self.assertEqual(len(union_set), 478)
        self.assertEqual(min(union_set), 0)
        self.assertEqual(max(union_set), 477)

        # Check non-overlapping disjoint properties
        self.assertTrue(eyebrows.isdisjoint(eyes))
        self.assertTrue(eyebrows.isdisjoint(lips))
        self.assertTrue(eyebrows.isdisjoint(nose))
        self.assertTrue(eyebrows.isdisjoint(face_shape))
        self.assertTrue(eyes.isdisjoint(lips))
        self.assertTrue(eyes.isdisjoint(nose))
        self.assertTrue(eyes.isdisjoint(face_shape))
        self.assertTrue(lips.isdisjoint(nose))
        self.assertTrue(lips.isdisjoint(face_shape))
        self.assertTrue(nose.isdisjoint(face_shape))

    def test_get_landmarks_for_density_sparse(self):
        """Verify sparse resolver returns standard landmark groups for active facial parts."""
        res = landmarks_config.get_landmarks_for_density("Sparse (Standard - 31 pts)", ["Nose", "Eyebrows"])
        # Expected keys should be exactly keys of the sparse nose and eyes-authored eyebrow groups.
        expected_keys = set(landmarks_config.LANDMARK_GROUPS["nose"].keys())
        expected_keys.update(landmarks_config.LANDMARK_GROUPS["eyebrows"].keys())
        self.assertEqual(set(res.keys()), expected_keys)
        self.assertEqual(res["sparse_nose_tip"], 4)
        self.assertEqual(res["sparse_eyes_left_eyebrow_1"], 107)

    def test_get_landmarks_for_density_dense(self):
        """Verify dense resolver returns sequential contours and nose sparse/contour points."""
        # Nose is included in the active set on purpose: Dense mode has a non-obvious
        # branch (landmarks_config.py:258-260) that merges the SPARSE Nose landmark
        # names alongside the Nose contours. Locking the full key set catches any drift.
        res = landmarks_config.get_landmarks_for_density("Dense (Contours - 149 pts)", ["Eyebrows", "Eyes", "Nose"])

        # Check that Eyebrows contour tracks are in the resolved set
        self.assertIn("dense_eyes_left_eyebrow_0", res)
        self.assertIn("dense_eyes_right_eyebrow_0", res)

        # Check that Eyes and Irises contour tracks are in the resolved set
        self.assertIn("dense_eyes_left_eye_0", res)
        self.assertIn("dense_eyes_right_eye_0", res)
        self.assertIn("dense_eyes_left_iris", res)
        self.assertIn("dense_eyes_right_iris", res)

        # Full expected key set: sparse Nose names (non-obvious inclusion) plus the
        # indexed contour points for every contour group owned by the active parts.
        expected_keys = set()
        for part in ("nose", "eyes", "eyebrows"):
            expected_keys.update(landmarks_config.PROFILE_LANDMARKS["dense"][part].keys())
        self.assertEqual(set(res.keys()), expected_keys)

    def test_get_landmarks_for_density_full(self):
        """Verify full resolver returns authored full profile points."""
        res = landmarks_config.get_landmarks_for_density("Full (Entire Mesh & Iris - 478 pts)", ["Eyebrows"])
        expected_keys = set(landmarks_config.PROFILE_LANDMARKS["full"]["eyebrows"].keys())
        self.assertEqual(set(res.keys()), expected_keys)
        self.assertEqual(res["full_eyebrows_right_eyebrow_7"], 70)

    def test_get_landmarks_for_analysis_includes_export_superset(self):
        """Analysis should record enough data for later Sparse/Dense/Surface/Full exports."""
        res = landmarks_config.get_landmarks_for_analysis()

        self.assertIn("sparse_face_chin", res)
        self.assertIn("dense_face_oval_0", res)
        self.assertIn("full_face_oval_14", res)
        self.assertIn("sparse_nose_tip", res)
        self.assertIn("dense_eyes_left_eye_0", res)
        self.assertIn("grid_r01_c01", res)
        self.assertIn("full_eyes_right_iris_4", res)

    def test_roto_contours_are_explicit_subset_of_contour_groups(self):
        """Roto should remain limited to spline-friendly contour groups, not surface point clouds."""
        roto_names = landmarks_config.get_roto_contour_names()

        self.assertTrue(roto_names)
        self.assertTrue(set(roto_names).issubset(set(landmarks_config.CONTOUR_GROUPS.keys())))
        self.assertNotIn("dense_face_left_cheek_0", roto_names)
        self.assertNotIn("dense_face_right_cheek_0", roto_names)
        self.assertFalse(any(name.startswith("Surface_") for name in roto_names))

    def test_iris_contours_exclude_centers(self):
        """Verify that Left_Iris and Right_Iris contour lists have exactly 4 points and do not include the centers."""
        left_iris_contour = landmarks_config.CONTOUR_GROUPS["roto_eyes_left_iris"]
        right_iris_contour = landmarks_config.CONTOUR_GROUPS["roto_eyes_right_iris"]

        self.assertEqual(len(left_iris_contour), 4)
        self.assertEqual(len(right_iris_contour), 4)

        # Verify center points (468, 473) are not in the contour boundaries
        self.assertNotIn(468, left_iris_contour)
        self.assertNotIn(473, right_iris_contour)

    def test_nostril_contours(self):
        """Verify that Left and Right Nostril contours contain the standard 6 points defining the nostrils."""
        left_nostril = landmarks_config.CONTOUR_GROUPS["roto_nose_left_nostril"]
        right_nostril = landmarks_config.CONTOUR_GROUPS["roto_nose_right_nostril"]

        self.assertEqual(len(left_nostril), 6)
        self.assertEqual(len(right_nostril), 6)

        # Verify standard landmarks are in the sets
        self.assertTrue(set([20, 60, 75, 79, 166, 238]).issubset(set(left_nostril)))
        self.assertTrue(set([250, 290, 305, 309, 392, 458]).issubset(set(right_nostril)))

    def test_merge_results_averaging_and_gap_patching(self):
        """Test merge_results for landmarks and contours averaging and gap patching."""
        forward = {
            "Nose_Tip": {
                "1": [10.0, 20.0],
                "2": [12.0, 22.0]
            },
            "Lips_Outer": {
                "1": [[1.0, 2.0], [3.0, 4.0]],
                "2": [[5.0, 6.0], [7.0, 8.0]]
            }
        }
        backward = {
            "Nose_Tip": {
                "2": [14.0, 24.0],
                "3": [16.0, 26.0]
            },
            "Lips_Outer": {
                "2": [[7.0, 8.0], [9.0, 10.0]],
                "3": [[11.0, 12.0], [13.0, 14.0]]
            }
        }

        contours_to_track = {"Lips_Outer": [0, 1]}
        landmarks_to_track = {"Nose_Tip": 4}

        merged = tracker_backend.merge_results(forward, backward, contours_to_track, landmarks_to_track)

        # Verify Nose_Tip
        # Frame 1: Only in forward -> [10.0, 20.0]
        self.assertEqual(merged["Nose_Tip"]["1"], [10.0, 20.0])
        # Frame 2: In both -> average: (12+14)/2 = 13.0, (22+24)/2 = 23.0
        self.assertEqual(merged["Nose_Tip"]["2"], [13.0, 23.0])
        # Frame 3: Only in backward -> [16.0, 26.0]
        self.assertEqual(merged["Nose_Tip"]["3"], [16.0, 26.0])

        # Verify Lips_Outer
        # Frame 1: Only forward -> [[1.0, 2.0], [3.0, 4.0]]
        self.assertEqual(merged["Lips_Outer"]["1"], [[1.0, 2.0], [3.0, 4.0]])
        # Frame 2: In both -> average of matching points
        self.assertEqual(merged["Lips_Outer"]["2"], [[6.0, 7.0], [8.0, 9.0]])
        # Frame 3: Only backward -> [[11.0, 12.0], [13.0, 14.0]]
        self.assertEqual(merged["Lips_Outer"]["3"], [[11.0, 12.0], [13.0, 14.0]])

    def test_to_nuke_xy_y_flip_and_scaling(self):
        """Verify _to_nuke_xy flips y, scales x by width, and rounds to 3 decimals.

        MediaPipe landmarks are normalized [0,1] with origin at top-left; Nuke
        uses pixel coordinates with origin at bottom-left, so y is flipped.
        """
        class _FakeLM:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        width, height = 1920, 1080

        # Top edge (lm.y == 0) maps to the bottom of the Nuke frame (y == height).
        top = tracker_backend._to_nuke_xy(_FakeLM(0.0, 0.0), width, height)
        self.assertEqual(top, [0.0, 1080.0])

        # Bottom edge (lm.y == 1) maps to the top of the Nuke frame (y == 0).
        bottom = tracker_backend._to_nuke_xy(_FakeLM(0.0, 1.0), width, height)
        self.assertEqual(bottom, [0.0, 0.0])

        # x scales by width, y is flipped and scaled by height.
        corner = tracker_backend._to_nuke_xy(_FakeLM(1.0, 1.0), width, height)
        self.assertEqual(corner, [1920.0, 0.0])

        # Rounding to 3 decimals is preserved (0.5 * 1080 = 540.0; 0.1234 * 1920 = 236.928).
        mid = tracker_backend._to_nuke_xy(_FakeLM(0.1234, 0.5), width, height)
        self.assertEqual(mid, [round(0.1234 * 1920, 3), round(1080 - (0.5 * 1080), 3)])
        self.assertEqual(mid, [236.928, 540.0])

    def test_merge_results_zip_truncation(self):
        """Lock the current zip-truncation behavior of _avg_points (tracker_backend.py:179).

        When forward and backward lists differ in length, zip() silently drops the
        trailing elements of the longer list instead of raising or padding. This
        test documents the existing behavior so a future change is caught.
        """
        forward = {
            "Lips_Outer": {
                "2": [[1.0, 2.0], [3.0, 4.0]]  # 2 points
            }
        }
        backward = {
            "Lips_Outer": {
                "2": [[5.0, 6.0], [7.0, 8.0], [9.0, 10.0]]  # 3 points
            }
        }
        merged = tracker_backend.merge_results(forward, backward, {"Lips_Outer": [0, 1]}, {})

        # Merged count matches the shorter (forward) list: the extra backward
        # point is silently dropped. Averaging is coordinate-wise over the pairs.
        self.assertEqual(len(merged["Lips_Outer"]["2"]), 2)
        self.assertEqual(merged["Lips_Outer"]["2"], [[3.0, 4.0], [5.0, 6.0]])

    def test_merge_results_empty_inputs(self):
        """merge_results over empty forward/backward passes yields empty per-key frame dicts."""
        merged = tracker_backend.merge_results({}, {}, {"Lips_Outer": [0, 1]}, {"Nose_Tip": 4})
        self.assertEqual(merged, {"Lips_Outer": {}, "Nose_Tip": {}})

    def test_merge_results_no_overlap(self):
        """Frames present in only one pass keep that pass's value unchanged."""
        forward = {"Lips_Outer": {"1": [[1.0, 2.0]]}}
        backward = {"Lips_Outer": {"2": [[3.0, 4.0]]}}
        merged = tracker_backend.merge_results(forward, backward, {"Lips_Outer": [0, 1]}, {})
        self.assertEqual(merged["Lips_Outer"]["1"], [[1.0, 2.0]])
        self.assertEqual(merged["Lips_Outer"]["2"], [[3.0, 4.0]])

    def test_get_frame_path_negative_frame(self):
        """Negative frames produce a leading '-': %04d of -5 -> '-005'.

        TODO: The current negative handling is likely wrong for VFX frame ranges
        (negative frame numbers are common in Nuke). Locking the existing output
        here so a future fix is intentional; production code is out of scope.
        """
        path = tracker_backend.get_frame_path("D:/footage/shot_01/shot_01.####.png", -5)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.-005.png")

    def test_get_frame_path_frame_zero(self):
        """Frame 0 zero-pads to the hash width: %04d of 0 -> '0000'."""
        path = tracker_backend.get_frame_path("D:/footage/shot_01/shot_01.####.png", 0)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.0000.png")

    def test_get_frame_path_frame_wider_than_hash_count(self):
        """A frame wider than the hash count overflows without truncation: %04d of 10000 -> '10000'."""
        path = tracker_backend.get_frame_path("D:/footage/shot_01/shot_01.####.png", 10000)
        self.assertEqual(path, "D:/footage/shot_01/shot_01.10000.png")

if __name__ == "__main__":
    unittest.main()
