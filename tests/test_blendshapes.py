import os
import sys
import json
import unittest
import tempfile
import shutil

# Ensure backend and frontend are in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

import blendshapes_config
from tracker_backend import _serialize_blendshapes


class MockCategory:
    def __init__(self, name, score):
        self.category_name = name
        self.score = score


class TestBlendshapes(unittest.TestCase):
    
    def test_blendshape_serialization(self):
        """Test that _serialize_blendshapes correctly converts objects into a dict of rounded scores."""
        mock_categories = [
            MockCategory("_neutral", 0.0000001),
            MockCategory("browDownLeft", 0.54321),
            MockCategory("jawOpen", 0.99999)
        ]
        
        result = _serialize_blendshapes(mock_categories)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["_neutral"], 0.0)
        self.assertEqual(result["browDownLeft"], 0.5432)
        self.assertEqual(result["jawOpen"], 1.0)

    def test_arkit_names_order(self):
        """Test that ARKIT_BLENDSHAPE_NAMES has 52 items and correct key ordering."""
        names = blendshapes_config.ARKIT_BLENDSHAPE_NAMES
        
        self.assertEqual(len(names), 52)
        # Verify index 0 is _neutral
        self.assertEqual(names[0], "_neutral")
        # Verify specific known indices based on ARKit standard (MediaPipe order)
        self.assertEqual(names[9], "eyeBlinkLeft")
        self.assertEqual(names[25], "jawOpen")

    def test_load_tracker_json_ignores_sidecar(self):
        """Test that existing trackers can read the main JSON without being affected by the sidecar."""
        from unittest.mock import MagicMock
        sys.modules['nuke'] = MagicMock()
        import nuke_tracker
        
        temp_dir = tempfile.mkdtemp()
        try:
            main_json = os.path.join(temp_dir, "tracker_data.json")
            sidecar_json = os.path.join(temp_dir, "tracker_data.blendshapes.json")
            
            # Create mock main tracker data
            main_data = {"1": {"face_contour": [[100, 100], [200, 200]]}}
            with open(main_json, "w") as f:
                json.dump(main_data, f)
                
            # Create mock blendshapes sidecar
            sidecar_data = {"1": {"_neutral": 0.0, "jawOpen": 1.0}}
            with open(sidecar_json, "w") as f:
                json.dump(sidecar_data, f)
                
            # Attempt to load blendshapes via nuke_tracker's function
            loaded_bs = nuke_tracker._load_blendshapes(main_json)
            self.assertEqual(loaded_bs, sidecar_data)
            
            # Verify standard loading doesn't implicitly pull sidecar data into the main load
            with open(main_json, "r") as f:
                loaded_main = json.load(f)
                
            self.assertIn("face_contour", loaded_main["1"])
            self.assertNotIn("jawOpen", loaded_main["1"])
            self.assertNotIn("_neutral", loaded_main["1"])
        finally:
            shutil.rmtree(temp_dir)

if __name__ == '__main__':
    unittest.main()
