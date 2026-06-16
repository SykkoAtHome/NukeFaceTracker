import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 1. Setup paths to import frontend and backend scripts
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(project_root, "frontend")
backend_dir = os.path.join(project_root, "backend")

if frontend_dir not in sys.path:
    sys.path.append(frontend_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# 2. Mock Nuke Python API prior to importing nuke_tracker
mock_nuke = MagicMock()
sys.modules['nuke'] = mock_nuke

# Now import nuke_tracker with mocked nuke module
import nuke_tracker


class TestTrackerRefinement(unittest.TestCase):

    def setUp(self):
        # Reset mock calls on each test run
        mock_nuke.reset_mock()

    class _FakeAnimCurve:
        def __init__(self):
            self.keys = []

        def addKey(self, frame, value):
            self.keys.append((frame, value))

    class _FakeAnimPoint:
        def __init__(self):
            self.curves = [TestTrackerRefinement._FakeAnimCurve(), TestTrackerRefinement._FakeAnimCurve()]

        def getPositionAnimCurve(self, dimension, _view):
            return self.curves[dimension]

    class _FakeControlPoint:
        def __init__(self):
            self.center = TestTrackerRefinement._FakeAnimPoint()
            self.leftTangent = TestTrackerRefinement._FakeAnimPoint()
            self.rightTangent = TestTrackerRefinement._FakeAnimPoint()
            self.featherCenter = TestTrackerRefinement._FakeAnimPoint()
            self.featherLeftTangent = TestTrackerRefinement._FakeAnimPoint()
            self.featherRightTangent = TestTrackerRefinement._FakeAnimPoint()

    def test_apply_smartvector_refinement_tracker(self):
        """Test Spring-Anchor refinement for standard Tracker4 format (single point per landmark)."""

        # Mock knobs
        mock_stiffness = MagicMock()
        mock_stiffness.value.return_name = "anchor_stiffness"
        mock_stiffness.value.return_value = 0.1 # Stiffness w = 0.1

        mock_refine_node = MagicMock()
        mock_refine_node.__getitem__.side_dict = {
            'anchor_stiffness': mock_stiffness
        }
        mock_refine_node.__getitem__.side_effect = lambda key: mock_refine_node.__getitem__.side_dict[key]

        # Mock SmartVector input node
        mock_vector_node = MagicMock()
        mock_vector_node.channels.return_value = ['smartvector_fwd.u', 'smartvector_fwd.v']
        # Mock sample function to return synthesized vector values
        # On frame 1: let's say (u, v) = (5.0, -2.0)
        mock_vector_node.sample.side_effect = lambda channel, x, y: 5.0 if channel == 'smartvector_fwd.u' else -2.0

        # Set node's inputs: node.input(1) returns the SmartVector node
        mock_refine_node.input.side_effect = lambda idx: mock_vector_node if idx == 1 else MagicMock()

        # Synthesize MediaPipe tracking data
        # Nose_Tip initially at [100.0, 200.0] on frame 1, and [108.0, 195.0] on frame 2
        tracker_data = {
            "Nose_Tip": {
                "1": [100.0, 200.0],
                "2": [108.0, 195.0]
            }
        }

        # Call the refinement helper
        # Refine from frame 1 to frame 2
        success = nuke_tracker.apply_smartvector_refinement(
            node=mock_refine_node,
            tracker_data=tracker_data,
            start_frame=1,
            end_frame=2,
            task=None
        )

        self.assertTrue(success)

        # Let's verify the math:
        # P_prev = P_Refined[1] = [100.0, 200.0]
        # Advection Step (sample returned u=5.0, v=-2.0):
        # P_Motion[2] = [100.0 + 5.0, 200.0 - 2.0] = [105.0, 198.0]
        # Anchor Correction (w = 0.1, P_MP[2] = [108.0, 195.0]):
        # P_Refined[2] = (1 - w) * P_Motion[2] + w * P_MP[2]
        #              = 0.9 * [105.0, 198.0] + 0.1 * [108.0, 195.0]
        #              = [94.5 + 10.8, 178.2 + 19.5]
        #              = [105.3, 197.7]

        refined_coords = tracker_data["Nose_Tip"]["2"]
        self.assertAlmostEqual(refined_coords[0], 105.3, places=3)
        self.assertAlmostEqual(refined_coords[1], 197.7, places=3)

        # Verify mock calls
        mock_nuke.frame.assert_any_call(1) # Switching frame context to sample at f-1 (1)
        mock_vector_node.sample.assert_any_call('smartvector_fwd.u', 100.5, 200.5) # Sub-pixel center offset check
        mock_vector_node.sample.assert_any_call('smartvector_fwd.v', 100.5, 200.5)

    def test_apply_smartvector_refinement_roto(self):
        """Test Spring-Anchor refinement for Roto format (list of points per contour)."""

        # Mock knobs
        mock_stiffness = MagicMock()
        mock_stiffness.value.return_value = 0.2 # Stiffness w = 0.2

        mock_refine_node = MagicMock()
        mock_refine_node.__getitem__.side_effect = lambda key: mock_stiffness if key == 'anchor_stiffness' else MagicMock()

        # Mock SmartVector input node
        mock_vector_node = MagicMock()
        mock_vector_node.channels.return_value = ['forward.u', 'forward.v']
        # Mock sample function: return constant motion vectors
        mock_vector_node.sample.side_effect = lambda channel, x, y: 1.0 if channel == 'forward.u' else 3.0
        mock_refine_node.input.side_effect = lambda idx: mock_vector_node if idx == 1 else MagicMock()

        # Synthesize roto contour data for Face_Oval (2 points)
        # Frame 1: [[10.0, 20.0], [30.0, 40.0]]
        # Frame 2: [[12.0, 22.0], [32.0, 42.0]]
        tracker_data = {
            "Face_Oval": {
                "1": [[10.0, 20.0], [30.0, 40.0]],
                "2": [[12.0, 22.0], [32.0, 42.0]]
            }
        }

        # Call refinement helper
        success = nuke_tracker.apply_smartvector_refinement(
            node=mock_refine_node,
            tracker_data=tracker_data,
            start_frame=1,
            end_frame=2,
            task=None
        )

        self.assertTrue(success)

        # Math verification for point 1:
        # P_prev = [10.0, 20.0], Motion (u=1.0, v=3.0) -> P_Motion = [11.0, 23.0]
        # P_MP = [12.0, 22.0], w = 0.2
        # P_Refined = 0.8 * [11.0, 23.0] + 0.2 * [12.0, 22.0]
        #           = [8.8 + 2.4, 18.4 + 4.4] = [11.2, 22.8]

        # Math verification for point 2:
        # P_prev = [30.0, 40.0], Motion (u=1.0, v=3.0) -> P_Motion = [31.0, 43.0]
        # P_MP = [32.0, 42.0], w = 0.2
        # P_Refined = 0.8 * [31.0, 43.0] + 0.2 * [32.0, 42.0]
        #           = [24.8 + 6.4, 34.4 + 8.4] = [31.2, 42.8]

        refined_coords_1 = tracker_data["Face_Oval"]["2"][0]
        refined_coords_2 = tracker_data["Face_Oval"]["2"][1]

        self.assertAlmostEqual(refined_coords_1[0], 11.2, places=3)
        self.assertAlmostEqual(refined_coords_1[1], 22.8, places=3)
        self.assertAlmostEqual(refined_coords_2[0], 31.2, places=3)
        self.assertAlmostEqual(refined_coords_2[1], 42.8, places=3)

    def test_generate_tracker_node_selected_landmarks(self):
        """Test selected landmarks resolution for generate_tracker_node under Sparse, Dense, and Full configurations."""
        import json

        # 1. Mock parent_node with a side_dict for knob values
        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()

        # Helper to setup mock knob values
        def set_knobs(density_val, track_nose, track_eyes, track_eyebrows, track_mouth, track_contour):
            knobs = {
                'landmark_density': MagicMock(value=lambda: density_val),
                'track_nose': MagicMock(value=lambda: track_nose),
                'track_eyes': MagicMock(value=lambda: track_eyes),
                'track_eyebrows': MagicMock(value=lambda: track_eyebrows),
                'track_mouth': MagicMock(value=lambda: track_mouth),
                'track_contour': MagicMock(value=lambda: track_contour),
                'export_t': MagicMock(value=lambda: True),
                'export_r': MagicMock(value=lambda: False),
                'export_s': MagicMock(value=lambda: False),
                'export_cornerpin_tracker': MagicMock(value=lambda: False),
            }
            mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # 2. Mock open/json loading of files so generate_tracker_node reads our dummy tracker data
        dummy_data = {
            "Nose_Tip": {"1": [10.0, 20.0]},
            "Face_Oval_0": {"1": [30.0, 40.0]},
            "Left_Eye_0": {"1": [50.0, 60.0]},
            "Mesh_0": {"1": [70.0, 80.0]},
        }

        # Also mock nuke.createNode to avoid creating actual Nuke nodes, and mock nuke.allNodes
        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_data))):

            # Case A: Sparse, Nose selected
            set_knobs("Sparse", True, False, False, False, False)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)

            # Case B: Dense, Eyes and Nose selected
            # Under Dense: track_eyes maps to Left_Eye_i and Right_Eye_i; track_nose maps to standard Nose landmarks.
            set_knobs("Dense", True, True, False, False, False)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)

            # Case C: Full mode (now respects UI checkboxes per requirements)
            set_knobs("Full", True, True, True, True, True)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)

    def test_interpolate_missing_frames_single_points(self):
        """Test linear interpolation and constant extrapolation for a single point landmark (Tracker mode)."""
        # Frame 1: [10.0, 20.0]
        # Frame 3: [30.0, 40.0]
        # Frame 2 is missing. Start frame is 0, end frame is 4.
        # Expected output:
        # Frame 0: Extrapolated to [10.0, 20.0]
        # Frame 1: [10.0, 20.0]
        # Frame 2: Interpolated to [20.0, 30.0]
        # Frame 3: [30.0, 40.0]
        # Frame 4: Extrapolated to [30.0, 40.0]
        dummy_data = {
            "1": [10.0, 20.0],
            "3": [30.0, 40.0]
        }
        res = nuke_tracker.interpolate_missing_frames(dummy_data, start_frame=0, end_frame=4)

        self.assertEqual(res["0"], [10.0, 20.0])
        self.assertEqual(res["1"], [10.0, 20.0])
        self.assertEqual(res["2"], [20.0, 30.0])
        self.assertEqual(res["3"], [30.0, 40.0])
        self.assertEqual(res["4"], [30.0, 40.0])

    def test_interpolate_missing_frames_list_of_points(self):
        """Test linear interpolation and constant extrapolation for a list of points (Roto mode)."""
        # Two points in contour
        dummy_data = {
            "2": [[10.0, 20.0], [100.0, 200.0]],
            "4": [[30.0, 40.0], [300.0, 400.0]]
        }
        res = nuke_tracker.interpolate_missing_frames(dummy_data, start_frame=1, end_frame=5)

        self.assertEqual(res["1"], [[10.0, 20.0], [100.0, 200.0]])
        self.assertEqual(res["2"], [[10.0, 20.0], [100.0, 200.0]])
        self.assertEqual(res["3"], [[20.0, 30.0], [200.0, 300.0]])
        self.assertEqual(res["4"], [[30.0, 40.0], [300.0, 400.0]])
        self.assertEqual(res["5"], [[30.0, 40.0], [300.0, 400.0]])

    def test_generate_roto_node_bezier_enabled(self):
        """Test Roto node generation when 'roto_bezier' (Cusped Bezier) is False (unchecked = smooth Bezier enabled)."""
        import json

        # Mock parent_node with a side_dict for Roto knobs
        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = {
            'roto_oval': MagicMock(value=lambda: True),
            'roto_nose_bridge': MagicMock(value=lambda: False),
            'roto_left_nostril': MagicMock(value=lambda: False),
            'roto_right_nostril': MagicMock(value=lambda: False),
            'roto_lips_outer': MagicMock(value=lambda: False),
            'roto_lips_inner': MagicMock(value=lambda: False),
            'roto_left_eye': MagicMock(value=lambda: False),
            'roto_right_eye': MagicMock(value=lambda: False),
            'roto_left_iris': MagicMock(value=lambda: False),
            'roto_right_iris': MagicMock(value=lambda: False),
            'roto_left_eyebrow': MagicMock(value=lambda: False),
            'roto_right_eyebrow': MagicMock(value=lambda: False),
            'roto_bezier': MagicMock(value=lambda: False), # False = Unchecked = Smooth Bezier enabled
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 1),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # Mock dummy roto JSON contour data
        dummy_roto_data = {
            "Face_Oval": {
                "1": [[100.0, 200.0], [150.0, 250.0], [200.0, 220.0]]
            }
        }

        # Mock nuke.rotopaint
        mock_rp = MagicMock()
        sys.modules['nuke.rotopaint'] = mock_rp
        mock_nuke.rotopaint = mock_rp

        def create_anim_control_point(x, y):
            return TestTrackerRefinement._FakeControlPoint()

        mock_rp.AnimControlPoint.side_effect = create_anim_control_point

        appended_points = []
        def shape_append(item):
            appended_points.append(item)

        def shape_getitem(idx):
            return appended_points[idx]

        mock_shape = MagicMock()
        mock_shape.append.side_effect = shape_append
        mock_shape.__getitem__.side_effect = shape_getitem
        mock_rp.Shape.return_value = mock_shape

        mock_nuke.allNodes.return_value = []
        mock_nuke.createNode.return_value = MagicMock()

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_roto_data))):

            success = nuke_tracker.generate_roto_node(mock_parent, "dummy_roto.json", 1920, 1080)
            self.assertTrue(success)

            # Main Bezier and feather Bezier must receive identical point/tangent keys.
            for cp in appended_points:
                self.assertEqual(cp.center.curves[0].keys, cp.featherCenter.curves[0].keys)
                self.assertEqual(cp.center.curves[1].keys, cp.featherCenter.curves[1].keys)
                self.assertEqual(cp.leftTangent.curves[0].keys, cp.featherLeftTangent.curves[0].keys)
                self.assertEqual(cp.leftTangent.curves[1].keys, cp.featherLeftTangent.curves[1].keys)
                self.assertEqual(cp.rightTangent.curves[0].keys, cp.featherRightTangent.curves[0].keys)
                self.assertEqual(cp.rightTangent.curves[1].keys, cp.featherRightTangent.curves[1].keys)

            self.assertEqual(appended_points[0].leftTangent.curves[0].keys, [(1, 12.5)])
            self.assertEqual(appended_points[0].leftTangent.curves[1].keys, [(1, -7.5)])
            self.assertEqual(appended_points[0].rightTangent.curves[0].keys, [(1, -12.5)])
            self.assertEqual(appended_points[0].rightTangent.curves[1].keys, [(1, 7.5)])

    def test_generate_roto_node_bezier_disabled(self):
        """Test Roto node generation when 'roto_bezier' (Cusped Bezier) is True (checked = smooth Bezier disabled/cusped)."""
        import json

        # Mock parent_node with a side_dict for Roto knobs
        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = {
            'roto_oval': MagicMock(value=lambda: True),
            'roto_nose_bridge': MagicMock(value=lambda: False),
            'roto_left_nostril': MagicMock(value=lambda: False),
            'roto_right_nostril': MagicMock(value=lambda: False),
            'roto_lips_outer': MagicMock(value=lambda: False),
            'roto_lips_inner': MagicMock(value=lambda: False),
            'roto_left_eye': MagicMock(value=lambda: False),
            'roto_right_eye': MagicMock(value=lambda: False),
            'roto_left_iris': MagicMock(value=lambda: False),
            'roto_right_iris': MagicMock(value=lambda: False),
            'roto_left_eyebrow': MagicMock(value=lambda: False),
            'roto_right_eyebrow': MagicMock(value=lambda: False),
            'roto_bezier': MagicMock(value=lambda: True), # True = Checked = Sharp/cusped (no Bezier tangents computed)
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 1),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # Mock dummy roto JSON contour data
        dummy_roto_data = {
            "Face_Oval": {
                "1": [[100.0, 200.0], [150.0, 250.0], [200.0, 220.0]]
            }
        }

        # Mock nuke.rotopaint
        mock_rp = MagicMock()
        sys.modules['nuke.rotopaint'] = mock_rp
        mock_nuke.rotopaint = mock_rp

        # Setup shape control points mock
        mock_center = MagicMock()
        mock_lt = MagicMock()
        mock_rt = MagicMock()

        def create_anim_control_point(x, y):
            cp = MagicMock()
            cp.center = mock_center
            cp.leftTangent = mock_lt
            cp.rightTangent = mock_rt
            return cp

        mock_rp.AnimControlPoint.side_effect = create_anim_control_point

        appended_points = []
        def shape_append(item):
            appended_points.append(item)

        def shape_getitem(idx):
            return appended_points[idx]

        mock_shape = MagicMock()
        mock_shape.append.side_effect = shape_append
        mock_shape.__getitem__.side_effect = shape_getitem
        mock_rp.Shape.return_value = mock_shape

        mock_nuke.allNodes.return_value = []
        mock_nuke.createNode.return_value = MagicMock()

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_roto_data))):

            success = nuke_tracker.generate_roto_node(mock_parent, "dummy_roto.json", 1920, 1080)
            self.assertTrue(success)

            # Verify that getPositionAnimCurve was called on center, but NOT on left/right tangents
            mock_center.getPositionAnimCurve.assert_called()
            mock_lt.getPositionAnimCurve.assert_not_called()
            mock_rt.getPositionAnimCurve.assert_not_called()

    def test_generate_roto_node_nose_bridge_uses_open_contour_key(self):
        """Nose bridge roto should use the contour key and avoid closed-shape tangents."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = {
            'roto_oval': MagicMock(value=lambda: False),
            'roto_nose_bridge': MagicMock(value=lambda: True),
            'roto_left_nostril': MagicMock(value=lambda: False),
            'roto_right_nostril': MagicMock(value=lambda: False),
            'roto_lips_outer': MagicMock(value=lambda: False),
            'roto_lips_inner': MagicMock(value=lambda: False),
            'roto_left_eye': MagicMock(value=lambda: False),
            'roto_right_eye': MagicMock(value=lambda: False),
            'roto_left_iris': MagicMock(value=lambda: False),
            'roto_right_iris': MagicMock(value=lambda: False),
            'roto_left_eyebrow': MagicMock(value=lambda: False),
            'roto_right_eyebrow': MagicMock(value=lambda: False),
            'roto_bezier': MagicMock(value=lambda: False),
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 1),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        dummy_roto_data = {
            "Nose_Bridge_Contour": {
                "1": [[100.0, 200.0], [120.0, 220.0], [140.0, 230.0]]
            },
            "Nose_Bridge": {
                "1": [140.0, 230.0]
            }
        }

        mock_rp = MagicMock()
        sys.modules['nuke.rotopaint'] = mock_rp
        mock_nuke.rotopaint = mock_rp
        mock_rp.AnimControlPoint.side_effect = lambda x, y: TestTrackerRefinement._FakeControlPoint()

        appended_points = []
        mock_shape = MagicMock()
        mock_shape.append.side_effect = lambda item: appended_points.append(item)
        mock_shape.__getitem__.side_effect = lambda idx: appended_points[idx]
        mock_rp.Shape.return_value = mock_shape

        mock_nuke.allNodes.return_value = []
        mock_nuke.createNode.return_value = MagicMock()

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_roto_data))):
            success = nuke_tracker.generate_roto_node(mock_parent, "dummy_roto.json", 1920, 1080)

        self.assertTrue(success)
        self.assertEqual(len(appended_points), 3)
        for cp in appended_points:
            self.assertEqual(cp.leftTangent.curves[0].keys, [])
            self.assertEqual(cp.rightTangent.curves[0].keys, [])


if __name__ == "__main__":
    unittest.main()
