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

if __name__ == "__main__":
    unittest.main()
