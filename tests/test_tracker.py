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
        self.assertIn("Nose_Tip", res)
        self.assertEqual(res["Nose_Tip"], 4)

    def test_get_landmarks_by_names_specific(self):
        """Test retrieving specific landmarks by their names."""
        names = ["Nose_Tip", "Left_Eye_Outer"]
        res = landmarks_config.get_landmarks_by_names(names)
        self.assertEqual(len(res), 2)
        self.assertEqual(res["Nose_Tip"], 4)
        self.assertEqual(res["Left_Eye_Outer"], 263)

    def test_get_landmarks_by_names_mesh_and_contour(self):
        """Test dynamic mesh and contour landmarks name resolution."""
        names = ["Mesh_152", "Face_Oval_0", "Lips_Outer_1", "Invalid_Name", "Mesh_500", "Face_Oval_99"]
        res = landmarks_config.get_landmarks_by_names(names)
        self.assertEqual(len(res), 3)
        self.assertEqual(res["Mesh_152"], 152)
        self.assertEqual(res["Face_Oval_0"], 10) # 10 is index 0 in Face_Oval
        self.assertEqual(res["Lips_Outer_1"], 185) # 185 is index 1 in Lips_Outer

    def test_get_contour_groups_by_names_all(self):
        """Test retrieving all contour groups when no names are specified."""
        res = landmarks_config.get_contour_groups_by_names([])
        self.assertEqual(len(res), len(landmarks_config.CONTOUR_GROUPS))
        self.assertIn("Face_Oval", res)
        self.assertIn("Lips_Outer", res)

    def test_get_contour_groups_by_names_specific(self):
        """Test retrieving specific contour groups by name."""
        names = ["Lips_Outer", "Left_Eye"]
        res = landmarks_config.get_contour_groups_by_names(names)
        self.assertEqual(len(res), 2)
        self.assertEqual(res["Lips_Outer"], landmarks_config.CONTOUR_GROUPS["Lips_Outer"])
        self.assertEqual(res["Left_Eye"], landmarks_config.CONTOUR_GROUPS["Left_Eye"])

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
        self.assertEqual(landmarks_config.LANDMARK_GROUPS["Nose"]["Nose_Left_Alar"], 358)
        self.assertEqual(landmarks_config.LANDMARK_GROUPS["Nose"]["Nose_Right_Alar"], 129)

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
        # Expected keys should be exactly keys of landmarks_config.LANDMARK_GROUPS["Nose"] and ["Eyebrows"]
        expected_keys = set(landmarks_config.LANDMARK_GROUPS["Nose"].keys()) | set(landmarks_config.LANDMARK_GROUPS["Eyebrows"].keys())
        self.assertEqual(set(res.keys()), expected_keys)
        self.assertEqual(res["Nose_Tip"], 4)
        self.assertEqual(res["Left_Eyebrow_Outer"], 300)

    def test_get_landmarks_for_density_dense(self):
        """Verify dense resolver returns sequential contours and nose sparse/contour points."""
        res = landmarks_config.get_landmarks_for_density("Dense (Contours - 149 pts)", ["Eyebrows", "Eyes"])
        
        # Check that Eyebrows contour tracks are in the resolved set
        self.assertIn("Left_Eyebrow_0", res)
        self.assertIn("Right_Eyebrow_0", res)
        
        # Check that Eyes and Irises contour tracks are in the resolved set
        self.assertIn("Left_Eye_0", res)
        self.assertIn("Right_Eye_0", res)
        self.assertIn("Left_Iris_0", res)
        self.assertIn("Right_Iris_0", res)

    def test_get_landmarks_for_density_full(self):
        """Verify full resolver returns exact partition mesh indices prefixed with Mesh_."""
        res = landmarks_config.get_landmarks_for_density("Full (Entire Mesh & Iris - 478 pts)", ["Eyebrows"])
        expected_keys = {f"Mesh_{idx}" for idx in landmarks_config.EYEBROWS_MESH_INDICES}
        self.assertEqual(set(res.keys()), expected_keys)
        self.assertEqual(res["Mesh_70"], 70)

    def test_iris_contours_exclude_centers(self):
        """Verify that Left_Iris and Right_Iris contour lists have exactly 4 points and do not include the centers."""
        left_iris_contour = landmarks_config.CONTOUR_GROUPS["Left_Iris"]
        right_iris_contour = landmarks_config.CONTOUR_GROUPS["Right_Iris"]
        
        self.assertEqual(len(left_iris_contour), 4)
        self.assertEqual(len(right_iris_contour), 4)
        
        # Verify center points (468, 473) are not in the contour boundaries
        self.assertNotIn(468, left_iris_contour)
        self.assertNotIn(473, right_iris_contour)

    def test_nostril_contours(self):
        """Verify that Left and Right Nostril contours contain the standard 6 points defining the nostrils."""
        left_nostril = landmarks_config.CONTOUR_GROUPS["Nose_Left_Nostril"]
        right_nostril = landmarks_config.CONTOUR_GROUPS["Nose_Right_Nostril"]
        
        self.assertEqual(len(left_nostril), 6)
        self.assertEqual(len(right_nostril), 6)
        
        # Verify standard landmarks are in the sets
        self.assertTrue(set([250, 290, 305, 309, 392, 458]).issubset(set(left_nostril)))
        self.assertTrue(set([20, 60, 75, 79, 166, 238]).issubset(set(right_nostril)))

if __name__ == "__main__":
    unittest.main()
