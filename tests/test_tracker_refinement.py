import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

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
        mock_nuke.createNode.side_effect = None
        mock_nuke.allNodes.side_effect = None
        mock_nuke.frame.return_value = 1
        # Mock hygiene: ensure no stale nuke.rotopaint leaks between tests.
        # Roto tests install a fresh mock_rp each time; the cleanup removes any
        # leftover from sys.modules and mock_nuke so a non-roto test never sees a
        # prior test's rotopaint mock (fresh auto-mock on next attribute access).
        sys.modules.pop('nuke.rotopaint', None)
        self.addCleanup(self._cleanup_rotopaint_mock)

    def _cleanup_rotopaint_mock(self):
        sys.modules.pop('nuke.rotopaint', None)
        try:
            del mock_nuke.rotopaint
        except AttributeError:
            pass

    def test_export_context_helpers_handle_root_and_group_contexts(self):
        """Root exports must use explicit context without passing Root as filter arg."""
        root = MagicMock()
        root.Class.return_value = "Root"
        root_node = MagicMock()
        mock_nuke.root.return_value = root
        mock_nuke.allNodes.return_value = [root_node]

        nuke_tracker._deselect_nodes_in_context(root)

        mock_nuke.allNodes.assert_called_once_with(group=root)
        root_node.setSelected.assert_called_once_with(False)

        mock_nuke.reset_mock()
        root.Class.return_value = "Root"
        created_root_node = MagicMock()
        mock_nuke.createNode.return_value = created_root_node

        self.assertIs(nuke_tracker._create_node_in_context(root, "Tracker4"), created_root_node)

        root.__enter__.assert_called_once_with()
        root.__exit__.assert_called_once()
        mock_nuke.createNode.assert_called_once_with("Tracker4")

        mock_nuke.reset_mock()
        group = MagicMock()
        group.Class.return_value = "Group"
        group_node = MagicMock()
        mock_nuke.allNodes.return_value = [group_node]

        nuke_tracker._deselect_nodes_in_context(group)

        mock_nuke.allNodes.assert_called_once_with(group=group)
        group_node.setSelected.assert_called_once_with(False)

    def test_create_face_tracker_node_defaults_to_root_frame_range_without_input(self):
        """Analyze Face frame knobs should default to the project range."""
        node = MagicMock()
        node.input.return_value = None
        root = MagicMock()
        root.firstFrame.return_value = 101
        root.lastFrame.return_value = 240
        mock_nuke.root.return_value = root
        mock_nuke.createNode.side_effect = [node, MagicMock(), MagicMock(), MagicMock()]

        with patch("nuke_tracker._build_tracking_tab") as build_tracking_tab, \
             patch("nuke_tracker._build_tracker_tab"), \
             patch("nuke_tracker._build_roto_tab"), \
             patch("nuke_tracker._build_cornerpin_tab"), \
             patch("nuke_tracker._build_gridwarp_tab"), \
             patch("nuke_tracker._build_settings_tab"), \
             patch("nuke_tracker._ensure_unique_output_json"):
            created = nuke_tracker.create_face_tracker_node()

        self.assertIs(created, node)
        build_tracking_tab.assert_called_once_with(node, 101, 240)

    # Default Roto knob values shared by every Roto test. Each test overrides
    # only the knobs it cares about via make_roto_knobs(**overrides).
    _ROTO_KNOB_DEFAULTS = {
        **{knob_name: False for knob_name, _contour_name, _label, _default in nuke_tracker.get_roto_contour_knob_specs()},
        'roto_bezier': False,
        'start_frame': 1,
        'end_frame': 1,
    }

    def make_roto_knobs(self, **overrides):
        """Return a fresh roto_* knob dict (MagicMocks) mirroring the panel state.

        Mirrors the set_knobs helper used by the tracker tests: every knob is a
        MagicMock whose .value() returns the configured bool/int. Tests pass only
        the knobs that differ from the disabled-defaults baseline.
        """
        values = dict(self._ROTO_KNOB_DEFAULTS)
        values.update(overrides)
        return {key: MagicMock(value=lambda v=v: v) for key, v in values.items()}

    def test_roto_panel_groups_contours_by_face_part(self):
        groups = {group["label"]: group for group in nuke_tracker.get_roto_contour_groups()}

        self.assertIn("Face", groups)
        self.assertIn("Eyes", groups)
        self.assertIn("Mouth", groups)
        self.assertIn("Nose", groups)
        self.assertEqual(groups["Face"]["knob"], "roto_group_face")
        self.assertTrue(any(item["knob"] == "roto_face_symmetry_axis" for item in groups["Face"]["items"]))
        self.assertTrue(all(" / " not in item["label"] for group in groups.values() for item in group["items"]))

    def test_roto_group_selection_updates_child_knobs(self):
        face_group = next(group for group in nuke_tracker.get_roto_contour_groups() if group["label"] == "Face")
        child_knobs = {item["knob"]: MagicMock() for item in face_group["items"]}
        node = MagicMock()
        node.__getitem__.side_effect = lambda key: child_knobs[key]

        changed = nuke_tracker.set_roto_group_selection(node, "roto_group_face", False)

        self.assertTrue(changed)
        for child in child_knobs.values():
            child.setValue.assert_called_once_with(False)

    def test_knob_changed_script_handles_roto_group_toggles(self):
        script = nuke_tracker._build_knob_changed_script()

        self.assertIn("roto_group_", script)
        self.assertIn("set_roto_group_selection", script)

    def test_analysis_tracks_all_roto_export_contours(self):
        """Tracking stores all Roto-tab contours so export choices can be changed later."""
        mock_node = MagicMock()

        knobs = {
            'landmark_density': MagicMock(value=lambda: "Sparse (Standard - 31 pts)"),
            'track_nose': MagicMock(value=lambda: False),
            'track_eyes': MagicMock(value=lambda: False),
            'track_eyebrows': MagicMock(value=lambda: False),
            'track_mouth': MagicMock(value=lambda: False),
            'track_contour': MagicMock(value=lambda: False),
            'roto_oval': MagicMock(value=lambda: False),
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
        }
        mock_node.__getitem__.side_effect = lambda key: knobs[key]

        names = nuke_tracker.get_names_to_track_for_analysis(mock_node)

        self.assertTrue(set(nuke_tracker.get_roto_export_contour_names()).issubset(set(names)))
        self.assertIn("roto_mouth_mouth_inner", names)
        self.assertIn("roto_eyes_left_eye", names)
        self.assertIn("roto_nose_left_nostril", names)

    def test_analysis_tracks_tracker_export_superset(self):
        """Tracking stores enough tracker points for later Surface and Full exports."""
        mock_node = MagicMock()

        knobs = {
            'landmark_density': MagicMock(value=lambda: "Sparse (Standard)"),
            'track_nose': MagicMock(value=lambda: False),
            'track_eyes': MagicMock(value=lambda: False),
            'track_eyebrows': MagicMock(value=lambda: False),
            'track_mouth': MagicMock(value=lambda: False),
            'track_contour': MagicMock(value=lambda: True),
            'roto_oval': MagicMock(value=lambda: False),
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
        }
        mock_node.__getitem__.side_effect = lambda key: knobs[key]

        names = nuke_tracker.get_names_to_track_for_analysis(mock_node)

        self.assertIn("sparse_face_chin", names)
        self.assertIn("dense_face_oval_0", names)
        self.assertIn("full_face_oval_14", names)
        self.assertIn("grid_r01_c01", names)

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
        # Real format dimensions so get_landmarks_bbox clamping is exercised with numbers.
        mock_vector_node.format().width.return_value = 1920
        mock_vector_node.format().height.return_value = 1080
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
        # Real format dimensions so get_landmarks_bbox clamping is exercised with numbers.
        mock_vector_node.format().width.return_value = 1920
        mock_vector_node.format().height.return_value = 1080
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
        """Test selected landmarks resolution for generate_tracker_node under Sparse, Dense, Surface, and Full configurations.

        Beyond asserting success, inspect the serialized fromScript payload per
        density case to confirm the track-count header and the presence/absence of
        specific track names (mirroring the dense-contour and nose-alias tests).
        """
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
            "sparse_nose_tip": {"1": [10.0, 20.0]},
            "dense_nose_tip": {"1": [12.0, 22.0]},
            "dense_eyes_left_eye_0": {"1": [50.0, 60.0]},
            "dense_face_oval_0": {"1": [55.0, 65.0]},
            "full_face_oval_0": {"1": [70.0, 80.0]},
        }

        # Also mock nuke.createNode to avoid creating actual Nuke nodes, and mock nuke.allNodes
        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_tracks_knob = MagicMock()
        mock_tracker.__getitem__.return_value = mock_tracks_knob
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_data))):

            # Case A: Sparse, Nose selected -> only sparse_nose_tip has data -> 1 track.
            set_knobs("Sparse", True, False, False, False, False)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)
            from_script = mock_tracks_knob.fromScript.call_args.args[0]
            self.assertIn("{ 1 31 1 }", from_script)
            self.assertIn('"sparse_nose_tip"', from_script)
            self.assertNotIn('"dense_face_oval_0"', from_script)
            self.assertNotIn('"full_face_oval_0"', from_script)

            # Case B: Dense, Eyes and Nose selected -> dense_nose_tip + dense_eyes_left_eye_0 -> 2 tracks.
            set_knobs("Dense", True, True, False, False, False)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)
            from_script = mock_tracks_knob.fromScript.call_args.args[0]
            self.assertIn("{ 1 31 2 }", from_script)
            self.assertIn('"dense_nose_tip"', from_script)
            self.assertIn('"dense_eyes_left_eye_0"', from_script)
            self.assertNotIn('"dense_face_oval_0"', from_script)

            # Case C: Dense, Face selected -> dense_face_oval_0 -> 1 track.
            set_knobs("Dense", False, False, False, False, True)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)
            from_script = mock_tracks_knob.fromScript.call_args.args[0]
            self.assertIn("{ 1 31 1 }", from_script)
            self.assertIn('"dense_face_oval_0"', from_script)
            self.assertNotIn('"sparse_nose_tip"', from_script)

            # Case D: Full mode (respects UI checkboxes) -> full_face_oval_0 -> 1 track.
            set_knobs("Full", True, True, True, True, True)
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)
            self.assertTrue(success)
            from_script = mock_tracks_knob.fromScript.call_args.args[0]
            self.assertIn("{ 1 31 1 }", from_script)
            self.assertIn('"full_face_oval_0"', from_script)
            self.assertNotIn('"sparse_nose_tip"', from_script)
            self.assertNotIn('"dense_eyes_left_eye_0"', from_script)

    def test_generate_tracker_node_preserves_missing_detection_frames(self):
        """Tracker export should not synthesize keyframes for frames missing in backend JSON."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerSparse"
        mock_parent.parent.return_value = MagicMock()
        knobs = {
            'landmark_density': MagicMock(value=lambda: "Sparse"),
            'track_nose': MagicMock(value=lambda: True),
            'track_eyes': MagicMock(value=lambda: False),
            'track_eyebrows': MagicMock(value=lambda: False),
            'track_mouth': MagicMock(value=lambda: False),
            'track_contour': MagicMock(value=lambda: False),
            'export_t': MagicMock(value=lambda: True),
            'export_r': MagicMock(value=lambda: False),
            'export_s': MagicMock(value=lambda: False),
            'export_cornerpin_tracker': MagicMock(value=lambda: False),
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 3),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        tracker_data = {
            "sparse_nose_tip": {
                "1": [10.0, 20.0],
                "3": [30.0, 40.0],
            }
        }

        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_tracks_knob = MagicMock()
        mock_tracker.__getitem__.return_value = mock_tracks_knob
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(tracker_data))):
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)
        from_script = mock_tracks_knob.fromScript.call_args.args[0]
        self.assertIn("x1 10.0", from_script)
        self.assertIn("x3 30.0", from_script)
        self.assertNotIn("x2 20.0", from_script)

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

        knobs = self.make_roto_knobs(roto_face_chin=True, roto_bezier=False,
                                     start_frame=1, end_frame=1)
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # Mock dummy roto JSON contour data: 3 control points (closed contour).
        #   idx 0: (100, 200), idx 1: (150, 250), idx 2: (200, 220)
        # _calculate_closed_bezier_tangent(points, idx, tension=0.25):
        #   tangent = (next - prev) * 0.25
        # idx0: prev=points[2]=(200,220), next=points[1]=(150,250) -> (−50,30)*0.25=(−12.5,7.5)
        # idx1: prev=points[0]=(100,200), next=points[2]=(200,220) -> (100,20)*0.25=(25,5)
        # idx2: prev=points[1]=(150,250), next=points[0]=(100,200) -> (−50,−50)*0.25=(−12.5,−12.5)
        #   ^ wraparound: next index (2+1)%3 = 0 -> points[0]. This is the error-prone case.
        dummy_roto_data = {
            "roto_face_chin": {
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

            self.assertEqual(len(appended_points), 3)

            # Feather center is a relative offset in Nuke. It must stay at zero so the
            # feather curve does not get pushed away from the main spline.
            for cp in appended_points:
                self.assertEqual(cp.featherCenter.curves[0].keys, [(1, 0.0)])
                self.assertEqual(cp.featherCenter.curves[1].keys, [(1, 0.0)])
                self.assertEqual(cp.leftTangent.curves[0].keys, cp.featherLeftTangent.curves[0].keys)
                self.assertEqual(cp.leftTangent.curves[1].keys, cp.featherLeftTangent.curves[1].keys)
                self.assertEqual(cp.rightTangent.curves[0].keys, cp.featherRightTangent.curves[0].keys)
                self.assertEqual(cp.rightTangent.curves[1].keys, cp.featherRightTangent.curves[1].keys)

            # Assert exact left/right tangent keys for ALL three control points.
            # leftTangent stores (-tx, -ty); rightTangent stores (tx, ty).
            # idx0: tangent=(-12.5, 7.5)
            self.assertEqual(appended_points[0].leftTangent.curves[0].keys, [(1, 12.5)])
            self.assertEqual(appended_points[0].leftTangent.curves[1].keys, [(1, -7.5)])
            self.assertEqual(appended_points[0].rightTangent.curves[0].keys, [(1, -12.5)])
            self.assertEqual(appended_points[0].rightTangent.curves[1].keys, [(1, 7.5)])
            # idx1: tangent=(25, 5)
            self.assertEqual(appended_points[1].leftTangent.curves[0].keys, [(1, -25.0)])
            self.assertEqual(appended_points[1].leftTangent.curves[1].keys, [(1, -5.0)])
            self.assertEqual(appended_points[1].rightTangent.curves[0].keys, [(1, 25.0)])
            self.assertEqual(appended_points[1].rightTangent.curves[1].keys, [(1, 5.0)])
            # idx2: wraparound next=(2+1)%3=0 -> points[0]; tangent=(-12.5, -12.5)
            self.assertEqual(appended_points[2].leftTangent.curves[0].keys, [(1, 12.5)])
            self.assertEqual(appended_points[2].leftTangent.curves[1].keys, [(1, 12.5)])
            self.assertEqual(appended_points[2].rightTangent.curves[0].keys, [(1, -12.5)])
            self.assertEqual(appended_points[2].rightTangent.curves[1].keys, [(1, -12.5)])

    def test_generate_roto_node_bezier_disabled(self):
        """Test Roto node generation when 'roto_bezier' (Cusped Bezier) is True (checked = smooth Bezier disabled/cusped)."""
        import json

        # Mock parent_node with a side_dict for Roto knobs
        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = self.make_roto_knobs(roto_face_chin=True, roto_bezier=True,
                                     start_frame=1, end_frame=1)
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # Mock dummy roto JSON contour data
        dummy_roto_data = {
            "roto_face_chin": {
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

    def test_generate_roto_node_builds_at_first_frame_and_restores_current_frame(self):
        """Creating a Roto node from a later timeline frame must not stamp first-frame coordinates there."""
        import json

        mock_nuke.frame.return_value = 10

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = self.make_roto_knobs(roto_face_chin=True, roto_bezier=True,
                                     start_frame=1, end_frame=10)
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        dummy_roto_data = {
            "roto_face_chin": {
                "1": [[100.0, 200.0], [150.0, 250.0]],
                "10": [[110.0, 210.0], [160.0, 260.0]]
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
        frame_set_calls = [call.args[0] for call in mock_nuke.frame.call_args_list if call.args]
        self.assertEqual(frame_set_calls[0], 1)
        self.assertEqual(frame_set_calls[-1], 10)
        # Frame-10 center keys must be present on the first appended point...
        self.assertIn((10, 110.0), appended_points[0].center.curves[0].keys)
        self.assertIn((10, 210.0), appended_points[0].center.curves[1].keys)
        # ...and the first-frame (frame 1) center keys must also be present, proving
        # the build frame stamps the initial coordinates at frame 1 (not at the
        # timeline's current frame 10).
        self.assertIn((1, 100.0), appended_points[0].center.curves[0].keys)
        self.assertIn((1, 200.0), appended_points[0].center.curves[1].keys)

    def test_generate_roto_node_preserves_missing_detection_frames(self):
        """Roto export should not synthesize control-point keys for missing frames."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = self.make_roto_knobs(roto_face_chin=True, roto_bezier=True,
                                     start_frame=1, end_frame=3)
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        dummy_roto_data = {
            "roto_face_chin": {
                "1": [[100.0, 200.0], [150.0, 250.0]],
                "3": [[120.0, 220.0], [170.0, 270.0]],
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
        self.assertEqual(appended_points[0].center.curves[0].keys, [(1, 100.0), (3, 120.0)])
        self.assertEqual(appended_points[0].center.curves[1].keys, [(1, 200.0), (3, 220.0)])

    def test_generate_roto_node_open_mapping_contour_skips_closed_tangents(self):
        """Contours marked openSpline are emitted as native open Roto splines."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTrackerRoto"
        mock_parent.parent.return_value = MagicMock()

        knobs = self.make_roto_knobs(roto_face_chin=False, roto_face_symmetry_axis=True,
                                     roto_bezier=False, start_frame=1, end_frame=1)
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        dummy_roto_data = {
            "roto_face_symmetry_axis": {
                "1": [[100.0, 200.0], [120.0, 220.0], [140.0, 230.0]]
            }
        }

        mock_rp = MagicMock()
        sys.modules['nuke.rotopaint'] = mock_rp
        mock_nuke.rotopaint = mock_rp

        mock_shape = MagicMock()
        mock_shape.name = "roto_face_symmetry_axis"
        mock_shape.__getitem__.side_effect = [
            TestTrackerRefinement._FakeControlPoint(),
            TestTrackerRefinement._FakeControlPoint(),
            TestTrackerRefinement._FakeControlPoint(),
        ]
        mock_curves = MagicMock()
        mock_curves.rootLayer = [mock_shape]
        mock_open_roto = MagicMock()
        mock_open_roto.__getitem__.side_effect = lambda key: mock_curves if key == "curves" else MagicMock()
        mock_nuke.allNodes.return_value = []
        mock_nuke.nodePaste.return_value = mock_open_roto

        open_script = nuke_tracker._build_open_roto_node_script(
            dummy_roto_data,
            "Roto_Face_FaceTrackerRoto",
            1920,
            1080,
        )
        curves_script = nuke_tracker._build_open_roto_curves_script(dummy_roto_data, 1920, 1080)

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(dummy_roto_data))):
            success = nuke_tracker.generate_roto_node(mock_parent, "dummy_roto.json", 1920, 1080)

        self.assertTrue(success)
        self.assertIn("curvegroup roto_face_symmetry_axis 1049088 bezier", open_script)
        self.assertIn("{f 1056800}", open_script)
        self.assertIn("Roto_Face_FaceTrackerRoto", open_script)
        self.assertIn("curvegroup roto_face_symmetry_axis 1049088 bezier", curves_script)
        mock_rp.Shape.assert_not_called()
        mock_nuke.createNode.assert_not_called()
        mock_curves.fromScript.assert_not_called()
        mock_nuke.nodePaste.assert_called_once()

    def test_generate_tracker_node_expands_dense_contour_groups(self):
        """Dense tracker export expands grouped contour JSON into one Tracker4 track per point."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()

        knobs = {
            'landmark_density': MagicMock(value=lambda: "Dense"),
            'track_nose': MagicMock(value=lambda: False),
            'track_eyes': MagicMock(value=lambda: True),
            'track_eyebrows': MagicMock(value=lambda: True),
            'track_mouth': MagicMock(value=lambda: True),
            'track_contour': MagicMock(value=lambda: True),
            'export_t': MagicMock(value=lambda: True),
            'export_r': MagicMock(value=lambda: False),
            'export_s': MagicMock(value=lambda: False),
            'export_cornerpin_tracker': MagicMock(value=lambda: False),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        resolved_landmarks = nuke_tracker.landmarks_config.get_landmarks_for_density(
            "Dense",
            ["Eyes", "Eyebrows", "Mouth", "Face"],
        )
        grouped_contours = {
            name: {"1": [float(idx), float(idx + 100)]}
            for name, idx in resolved_landmarks.items()
        }

        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_tracks_knob = MagicMock()
        mock_tracker.__getitem__.return_value = mock_tracks_knob
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(grouped_contours))):
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)
        from_script = mock_tracks_knob.fromScript.call_args.args[0]
        expected_tracks = len(set(resolved_landmarks.values()))
        self.assertIn(f"{{ 1 31 {expected_tracks} }}", from_script)
        self.assertIn('"dense_face_oval_0"', from_script)
        self.assertIn('"dense_face_oval_8"', from_script)
        self.assertIn('"dense_eyes_right_eyebrow_5"', from_script)

    def test_generate_tracker_node_dedupes_dense_nose_aliases(self):
        """Dense tracker export emits one Tracker4 track per MediaPipe index."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()

        knobs = {
            'landmark_density': MagicMock(value=lambda: "Dense"),
            'track_nose': MagicMock(value=lambda: True),
            'track_eyes': MagicMock(value=lambda: False),
            'track_eyebrows': MagicMock(value=lambda: False),
            'track_mouth': MagicMock(value=lambda: False),
            'track_contour': MagicMock(value=lambda: False),
            'export_t': MagicMock(value=lambda: True),
            'export_r': MagicMock(value=lambda: False),
            'export_s': MagicMock(value=lambda: False),
            'export_cornerpin_tracker': MagicMock(value=lambda: False),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        resolved_landmarks = nuke_tracker.landmarks_config.get_landmarks_for_density("Dense", ["Nose"])
        tracker_data = {
            name: {"1": [float(idx), float(idx + 100)]}
            for name, idx in resolved_landmarks.items()
        }

        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_tracks_knob = MagicMock()
        mock_tracker.__getitem__.return_value = mock_tracks_knob
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(tracker_data))):
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)
        from_script = mock_tracks_knob.fromScript.call_args.args[0]
        expected_tracks = len(set(resolved_landmarks.values()))
        self.assertIn(f"{{ 1 31 {expected_tracks} }}", from_script)
        self.assertIn('"dense_nose_bridge_0"', from_script)
        self.assertIn('"dense_nose_tip"', from_script)
        self.assertIn('"dense_nose_columella"', from_script)

    # ------------------------------------------------------------------
    # find_vector_channels (frontend/nuke_tracker.py ~94-154)
    # ------------------------------------------------------------------

    def test_find_vector_channels_returns_none_for_empty(self):
        """No channel pair present -> (None, None)."""
        node = MagicMock()
        node.channels.return_value = ['rgba.red', 'rgba.green', 'rgba.blue']
        self.assertEqual(nuke_tracker.find_vector_channels(node), (None, None))

    def test_find_vector_channels_returns_none_for_none_node(self):
        """A falsy node -> (None, None) without touching channels()."""
        self.assertEqual(nuke_tracker.find_vector_channels(None), (None, None))

    def test_find_vector_channels_smartvector_fwd_beats_forward(self):
        """smartvector_fwd (score 110) beats forward (score 50) when both present."""
        node = MagicMock()
        node.channels.return_value = [
            'smartvector_fwd.u', 'smartvector_fwd.v',
            'forward.u', 'forward.v',
        ]
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'smartvector_fwd.u')
        self.assertEqual(v, 'smartvector_fwd.v')

    def test_find_vector_channels_forward_beats_motion(self):
        """forward (score 50) beats motion (score 30) when both present."""
        node = MagicMock()
        node.channels.return_value = [
            'forward.u', 'forward.v',
            'motion.u', 'motion.v',
        ]
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'forward.u')
        self.assertEqual(v, 'forward.v')

    def test_find_vector_channels_f01_beats_fwd(self):
        """smartvector_f01 (score 120) beats smartvector_fwd (score 110)."""
        node = MagicMock()
        node.channels.return_value = [
            'smartvector_f01.u', 'smartvector_f01.v',
            'smartvector_fwd.u', 'smartvector_fwd.v',
        ]
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'smartvector_f01.u')
        self.assertEqual(v, 'smartvector_f01.v')

    def test_find_vector_channels_u_v_preferred_over_x_y(self):
        """When a single layer exposes both .u/.v and .x/.y, the .u/.v pair wins."""
        node = MagicMock()
        node.channels.return_value = [
            'smartvector_fwd.u', 'smartvector_fwd.v',
            'smartvector_fwd.x', 'smartvector_fwd.y',
        ]
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'smartvector_fwd.u')
        self.assertEqual(v, 'smartvector_fwd.v')

    def test_find_vector_channels_falls_back_to_x_y(self):
        """A layer exposing only .x/.y is still accepted."""
        node = MagicMock()
        node.channels.return_value = ['motion.x', 'motion.y']
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'motion.x')
        self.assertEqual(v, 'motion.y')

    def test_find_vector_channels_generic_layer_lowest_score(self):
        """A layer with no recognized keyword (score 10) is still picked when alone."""
        node = MagicMock()
        node.channels.return_value = ['custom_uv.u', 'custom_uv.v']
        u, v = nuke_tracker.find_vector_channels(node)
        self.assertEqual(u, 'custom_uv.u')
        self.assertEqual(v, 'custom_uv.v')

    # ------------------------------------------------------------------
    # interpolate_missing_frames edge cases
    # ------------------------------------------------------------------

    def test_interpolate_missing_frames_empty_input(self):
        """Empty frame_data -> empty result (no data to interpolate)."""
        self.assertEqual(nuke_tracker.interpolate_missing_frames({}, 1, 10), {})

    def test_interpolate_missing_frames_single_frame_constant_extrapolation(self):
        """A single keyframe over a surrounding range is constant-extrapolated to
        every frame in [start, end] (no interpolation, just hold the value)."""
        dummy_data = {"5": [42.0, 99.0]}
        res = nuke_tracker.interpolate_missing_frames(dummy_data, start_frame=1, end_frame=10)
        self.assertEqual(len(res), 10)
        for f in range(1, 11):
            self.assertEqual(res[str(f)], [42.0, 99.0])

    def test_interpolate_missing_frames_single_frame_list_of_points(self):
        """Constant extrapolation also holds for the list-of-points (Roto) format."""
        dummy_data = {"3": [[10.0, 20.0], [30.0, 40.0]]}
        res = nuke_tracker.interpolate_missing_frames(dummy_data, start_frame=1, end_frame=5)
        self.assertEqual(len(res), 5)
        for f in range(1, 6):
            self.assertEqual(res[str(f)], [[10.0, 20.0], [30.0, 40.0]])

    def test_interpolate_missing_frames_numeric_not_lexicographic_sort(self):
        """Frame keys are sorted by int value, not lexicographically, so '10' is treated
        as later than '2' (lexicographic order would put '10' before '2')."""
        # Keyframes at frame 1 and frame 10; frame 5 interpolates between them.
        dummy_data = {"1": [0.0, 0.0], "10": [90.0, 180.0]}
        res = nuke_tracker.interpolate_missing_frames(dummy_data, start_frame=1, end_frame=10)
        # t at frame 5 = (5-1)/(10-1) = 4/9 -> x = 0 + 4/9*90 = 40.0, y = 0 + 4/9*180 = 80.0
        self.assertAlmostEqual(res["5"][0], 40.0, places=3)
        self.assertAlmostEqual(res["5"][1], 80.0, places=3)
        # Frame 2 is between 1 and 10 (not after 10, which lexicographic '10' < '2' would imply).
        self.assertAlmostEqual(res["2"][0], 10.0, places=3)
        self.assertAlmostEqual(res["2"][1], 20.0, places=3)

    # ------------------------------------------------------------------
    # get_landmarks_bbox clamping
    # ------------------------------------------------------------------

    def test_get_landmarks_bbox_clamps_out_of_bounds_coords(self):
        """Coordinates beyond the image boundary are clamped to [0, width] / [0, height]."""
        tracker_data = {
            "Nose_Tip": {"5": [-100.0, 5000.0]},  # x<0, y>height
        }
        bbox = nuke_tracker.get_landmarks_bbox(tracker_data, 5, width=1920, height=1080, padding=50)
        # x_min clamped to 0, y_max clamped to 1080; padding applied then clamped.
        self.assertEqual(bbox[0], 0)        # x_min >= 0
        self.assertLessEqual(bbox[2], 1920) # x_max <= width
        self.assertGreaterEqual(bbox[1], 0) # y_min >= 0
        self.assertLessEqual(bbox[3], 1080) # y_max <= height

    def test_get_landmarks_bbox_single_point_collapsed_fallback(self):
        """A single point collapses the bbox; the fallback widens it by +/-10 on each axis."""
        tracker_data = {"Nose_Tip": {"5": [100.0, 200.0]}}
        bbox = nuke_tracker.get_landmarks_bbox(tracker_data, 5, width=1920, height=1080, padding=50)
        # x_min = max(0, 100-50)=50, x_max = min(1920, 100+50)=150 -> collapsed (50<150 ok).
        # Single point: min==max for raw, but padding separates them. With a single
        # point x_min=50, x_max=150 (not collapsed). For the collapsed path we need
        # padding=0 so x_min==x_max triggers the +/-10 widening.
        bbox2 = nuke_tracker.get_landmarks_bbox(tracker_data, 5, width=1920, height=1080, padding=0)
        # x_min = max(0, 100-0)=100, x_max = min(1920, 100+0)=100 -> x_min>=x_max -> widen:
        # x_min = max(0, 100-10)=90, x_max = min(1920, 100+10)=110.
        self.assertEqual(bbox2[0], 90)
        self.assertEqual(bbox2[1], 190)
        self.assertEqual(bbox2[2], 110)
        self.assertEqual(bbox2[3], 210)

    def test_get_landmarks_bbox_empty_frame_returns_full_frame(self):
        """No data on the requested frame -> full-frame bbox [0,0,width,height]."""
        tracker_data = {"Nose_Tip": {"4": [10.0, 20.0]}}  # frame 5 absent
        bbox = nuke_tracker.get_landmarks_bbox(tracker_data, 5, width=1920, height=1080, padding=50)
        self.assertEqual(bbox, [0, 0, 1920, 1080])

    # ------------------------------------------------------------------
    # calculate_cornerpin_data + generate_cornerpin_node
    # ------------------------------------------------------------------

    def test_calculate_cornerpin_data_horizontal_eye_line(self):
        """theta=0 (horizontal eye line): corners equal the axis-aligned bbox in BL/BR/TR/TL order."""
        tracker_data = {
            # Four corner points defining the bbox (50,50)-(250,150).
            "P1": {"5": [50.0, 50.0]},
            "P2": {"5": [250.0, 50.0]},
            "P3": {"5": [250.0, 150.0]},
            "P4": {"5": [50.0, 150.0]},
            # Horizontal eye line at y=100 (theta = atan2(0, 80) = 0).
            "Right_Eye_Outer": {"5": [100.0, 100.0]},
            "Right_Eye_Inner": {"5": [120.0, 100.0]},
            "Left_Eye_Outer": {"5": [180.0, 100.0]},
            "Left_Eye_Inner": {"5": [200.0, 100.0]},
        }
        res = nuke_tracker.calculate_cornerpin_data(tracker_data, 1, 10, 1920, 1080)
        self.assertEqual(set(res.keys()), {5})
        self.assertEqual(res[5], [[50.0, 50.0], [250.0, 50.0], [250.0, 150.0], [50.0, 150.0]])

    def test_calculate_cornerpin_data_rotated_eye_line_90(self):
        """Eye line rotated +90deg: corners are the face-space AABB rotated back by +theta.

        Face space: bbox (0,0)-(200,100), center (100,50), eyes on the horizontal line
        y=50. Rotating the whole face by +90deg around (100,50) puts the eye line
        vertical (theta = +pi/2). The function must recover the face-space AABB and
        rotate the four corners back by +theta, yielding:
          BL=(150,-50), BR=(150,150), TR=(50,150), TL=(50,-50)
        which verifies the theta sign convention and the BL/BR/TR/TL ordering.
        """
        tracker_data = {
            # Image-space corners (face-space box rotated +90deg around (100,50)).
            "P1": {"5": [150.0, -50.0]},
            "P2": {"5": [150.0, 150.0]},
            "P3": {"5": [50.0, 150.0]},
            "P4": {"5": [50.0, -50.0]},
            # Image-space eye points: face-space y=50 -> vertical line x=100.
            "Right_Eye_Outer": {"5": [100.0, -10.0]},
            "Right_Eye_Inner": {"5": [100.0, 10.0]},
            "Left_Eye_Outer": {"5": [100.0, 90.0]},
            "Left_Eye_Inner": {"5": [100.0, 110.0]},
        }
        res = nuke_tracker.calculate_cornerpin_data(tracker_data, 1, 10, 1920, 1080)
        expected = [[150.0, -50.0], [150.0, 150.0], [50.0, 150.0], [50.0, -50.0]]
        self.assertEqual(set(res.keys()), {5})
        self.assertEqual(res[5], expected)

    def test_calculate_cornerpin_data_empty_input_returns_no_keyframes(self):
        """No detected landmarks should produce no synthetic CornerPin keys."""
        res = nuke_tracker.calculate_cornerpin_data({}, 1, 3, width=1920, height=1080)
        self.assertEqual(res, {})

    def test_generate_cornerpin_node_sets_to_and_from_keyframes(self):
        """generate_cornerpin_node sets constant 'to' knobs at the reference frame and
        animates 'from1..from4' with setValueAt per frame in BL/BR/TR/TL order."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()
        knobs = {
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 10),
            'ref_frame': MagicMock(value=lambda: 5),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # theta=0 synthetic data so corners are the AABB (50,50)-(250,150).
        tracker_data = {
            "P1": {"5": [50.0, 50.0]},
            "P2": {"5": [250.0, 50.0]},
            "P3": {"5": [250.0, 150.0]},
            "P4": {"5": [50.0, 150.0]},
            "Right_Eye_Outer": {"5": [100.0, 100.0]},
            "Right_Eye_Inner": {"5": [120.0, 100.0]},
            "Left_Eye_Outer": {"5": [180.0, 100.0]},
            "Left_Eye_Inner": {"5": [200.0, 100.0]},
        }

        mock_cornerpin = MagicMock()
        # Explicit per-knob mocks: a bare MagicMock.__getitem__ returns the same
        # child for every key, which would conflate from1..from4 and to1..to4. Map
        # each knob name to its own mock so call_count/assertions are per-knob.
        knob_mocks = {name: MagicMock() for name in (
            'to1', 'to2', 'to3', 'to4',
            'from1', 'from2', 'from3', 'from4',
            'label',
        )}
        mock_cornerpin.__getitem__.side_effect = lambda key: knob_mocks[key]
        mock_nuke.createNode.return_value = mock_cornerpin
        mock_nuke.allNodes.return_value = []

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(tracker_data))):
            success = nuke_tracker.generate_cornerpin_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)

        # 'to' knobs are constant and equal to the reference-frame (frame 5) corners.
        # ref_bbox = [[50,50],[250,50],[250,150],[50,150]].
        knob_mocks['to1'].setValue.assert_any_call([50.0, 50.0])    # BL
        knob_mocks['to2'].setValue.assert_any_call([250.0, 50.0])  # BR
        knob_mocks['to3'].setValue.assert_any_call([250.0, 150.0]) # TR
        knob_mocks['to4'].setValue.assert_any_call([50.0, 150.0])  # TL

        # 'from' knobs are animated but keyframed only where tracking data exists.
        for i in range(1, 5):
            self.assertTrue(knob_mocks[f'from{i}'].setAnimated.called)

        # Spot-check the BL/BR/TR/TL setValueAt calls at frame 5:
        # from1 (BL): (x=50, frame=5, dim=0), (y=50, frame=5, dim=1)
        knob_mocks['from1'].setValueAt.assert_any_call(50.0, 5, 0)
        knob_mocks['from1'].setValueAt.assert_any_call(50.0, 5, 1)
        # from2 (BR): (x=250, frame=5, dim=0), (y=50, frame=5, dim=1)
        knob_mocks['from2'].setValueAt.assert_any_call(250.0, 5, 0)
        knob_mocks['from2'].setValueAt.assert_any_call(50.0, 5, 1)
        # from3 (TR): (x=250, frame=5, dim=0), (y=150, frame=5, dim=1)
        knob_mocks['from3'].setValueAt.assert_any_call(250.0, 5, 0)
        knob_mocks['from3'].setValueAt.assert_any_call(150.0, 5, 1)
        # from4 (TL): (x=50, frame=5, dim=0), (y=150, frame=5, dim=1)
        knob_mocks['from4'].setValueAt.assert_any_call(50.0, 5, 0)
        knob_mocks['from4'].setValueAt.assert_any_call(150.0, 5, 1)

        # Total setValueAt calls per from knob: one (x,y) pair for frame 5 only.
        for i in range(1, 5):
            self.assertEqual(knob_mocks[f'from{i}'].setValueAt.call_count, 2)

    def test_generate_tracker_node_injects_cornerpin_tracks(self):
        """export_cornerpin_tracker=True injects Corner_BL/BR/TR/TL tracks into the Tracker4 node."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()
        knobs = {
            'landmark_density': MagicMock(value=lambda: "Sparse"),
            'track_nose': MagicMock(value=lambda: True),
            'track_eyes': MagicMock(value=lambda: False),
            'track_eyebrows': MagicMock(value=lambda: False),
            'track_mouth': MagicMock(value=lambda: False),
            'track_contour': MagicMock(value=lambda: False),
            'export_t': MagicMock(value=lambda: True),
            'export_r': MagicMock(value=lambda: False),
            'export_s': MagicMock(value=lambda: False),
            'export_cornerpin_tracker': MagicMock(value=lambda: True),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        # theta=0 synthetic data: AABB (50,50)-(250,150) for the corner tracks.
        tracker_data = {
            "sparse_nose_tip": {"5": [10.0, 20.0]},
            "P1": {"5": [50.0, 50.0]},
            "P2": {"5": [250.0, 50.0]},
            "P3": {"5": [250.0, 150.0]},
            "P4": {"5": [50.0, 150.0]},
            "Right_Eye_Outer": {"5": [100.0, 100.0]},
            "Right_Eye_Inner": {"5": [120.0, 100.0]},
            "Left_Eye_Outer": {"5": [180.0, 100.0]},
            "Left_Eye_Inner": {"5": [200.0, 100.0]},
        }

        mock_nuke.allNodes.return_value = []
        mock_tracker = MagicMock()
        mock_tracks_knob = MagicMock()
        mock_tracker.__getitem__.return_value = mock_tracks_knob
        mock_nuke.createNode.return_value = mock_tracker

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(tracker_data))):
            success = nuke_tracker.generate_tracker_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)
        from_script = mock_tracks_knob.fromScript.call_args.args[0]
        # Sparse + Nose resolves only sparse_nose_tip (1 track) + 4 corner tracks = 5 total.
        self.assertIn("{ 1 31 5 }", from_script)
        self.assertIn('"sparse_nose_tip"', from_script)
        self.assertIn('"Corner_BL"', from_script)
        self.assertIn('"Corner_BR"', from_script)
        self.assertIn('"Corner_TR"', from_script)
        self.assertIn('"Corner_TL"', from_script)

    def test_gridwarp_payload_preserves_missing_detection_frames(self):
        """GridWarp payload should include only frames with a complete detected grid."""
        tracker_data = {}
        for name, idx in nuke_tracker.landmarks_config.get_grid_landmarks().items():
            tracker_data[name] = {
                "1": [float(idx), float(idx + 100)],
                "3": [float(idx + 10), float(idx + 110)],
            }

        payload, err = nuke_tracker._grid_payload_from_tracks(tracker_data, 1, 3, 1)

        self.assertIsNone(err)
        self.assertEqual(set(payload["source"].keys()), {"1", "3"})
        self.assertEqual(payload["reference_frame"], 1)

    def test_gridwarp_scripts_target_native_grid_knobs(self):
        """GridWarp scripts must match Nuke's source_grid_col/destination_grid_col payload shape."""
        payload = {
            "rows": 2,
            "cols": 2,
            "reference_frame": 1,
            "destination": [
                {"row": 0, "col": 0, "id": 1, "x": 10.0, "y": 20.0},
                {"row": 0, "col": 1, "id": 2, "x": 40.0, "y": 20.0},
                {"row": 1, "col": 0, "id": 3, "x": 10.0, "y": 80.0},
                {"row": 1, "col": 1, "id": 4, "x": 40.0, "y": 80.0},
            ],
            "source": {
                "1": [
                    {"row": 0, "col": 0, "x": 11.0, "y": 21.0},
                    {"row": 0, "col": 1, "x": 41.0, "y": 21.0},
                    {"row": 1, "col": 0, "x": 11.0, "y": 81.0},
                    {"row": 1, "col": 1, "x": 41.0, "y": 81.0},
                ],
                "5": [
                    {"row": 0, "col": 0, "x": 12.0, "y": 22.0},
                    {"row": 0, "col": 1, "x": 42.0, "y": 22.0},
                    {"row": 1, "col": 0, "x": 12.0, "y": 82.0},
                    {"row": 1, "col": 1, "x": 42.0, "y": 82.0},
                ],
            },
        }

        source_script = nuke_tracker._build_gridwarp_source_script(payload)
        destination_script = nuke_tracker._build_gridwarp_destination_script(payload)
        node_script = nuke_tracker._build_gridwarp_node_script(payload, "GridWarp_Face_Test")

        self.assertIn("1 2 2 4 1 0", source_script)
        self.assertIn("{curve L x1 11 x5 12}", source_script)
        self.assertIn("{curve L x1 21 x5 22}", source_script)
        self.assertIn("{curve L x1 10 x5 10}", source_script)
        self.assertIn("1 2 2 4 1 0", destination_script)
        self.assertIn("{2 10 20}", destination_script)
        self.assertIn("{2 10 0}", destination_script)
        self.assertNotIn("facetracker_grid_payload", source_script)
        self.assertNotIn("facetracker_grid_payload", destination_script)
        self.assertIn("GridWarp3 {", node_script)
        self.assertIn("source_grid_col", node_script)
        self.assertIn("destination_grid_col", node_script)
        self.assertIn("source_grid_transform_center {25 50}", node_script)

    def test_generate_gridwarp_node_populates_native_grid_knobs(self):
        """GridWarp export pastes a complete native GridWarp script instead of editing default grid knobs."""
        import json

        mock_parent = MagicMock()
        mock_parent.name.return_value = "FaceTracker1"
        mock_parent.parent.return_value = MagicMock()
        knobs = {
            'start_frame': MagicMock(value=lambda: 1),
            'end_frame': MagicMock(value=lambda: 2),
            'grid_ref_frame': MagicMock(value=lambda: 1),
        }
        mock_parent.__getitem__.side_effect = lambda key: knobs[key]

        tracker_data = {}
        for point in nuke_tracker._grid_points_from_mapping()[2]:
            tracker_data[point["track"]] = {
                "1": [float(point["col"] * 10), float(point["row"] * 20)],
                "2": [float(point["col"] * 10 + 1), float(point["row"] * 20 + 2)],
            }

        mock_gridwarp = MagicMock()
        mock_nuke.nodePaste.return_value = mock_gridwarp
        mock_nuke.allNodes.return_value = []

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(tracker_data))):
            success = nuke_tracker.generate_gridwarp_node(mock_parent, "dummy.json", 1920, 1080)

        self.assertTrue(success)
        mock_nuke.createNode.assert_not_called()
        mock_nuke.nodePaste.assert_called_once()
        paste_path = mock_nuke.nodePaste.call_args.args[0]
        self.assertTrue(os.path.basename(paste_path).startswith("facetracker_gridwarp_"))
        mock_gridwarp.addKnob.assert_not_called()


# ---------------------------------------------------------------------------
# run_tracking_on_node orchestration tests (the Track-Face entry point).
# These use the module-level mock_nuke (the same object nuke_tracker bound to
# `nuke` at import) and a mocked subprocess so no real backend ever runs.
# ---------------------------------------------------------------------------


class _FakeStdout:
    """Yields scripted stdout lines then EOF (readline -> "") for the reader thread."""

    def __init__(self, lines):
        self._lines = list(lines)
        self._i = 0
        self.closed = False

    def readline(self):
        if self._i < len(self._lines):
            line = self._lines[self._i]
            self._i += 1
            return line
        self.closed = True
        return ""


class _SlowFirstLineStdout(_FakeStdout):
    """Delays first output long enough to trigger Queue.Empty in the parent loop."""

    def __init__(self, lines, delay=0.2):
        super().__init__(lines)
        self._delay = delay
        self._slept = False

    def readline(self):
        if not self._slept:
            self._slept = True
            time.sleep(self._delay)
        return super().readline()


class _FakeProcess:
    """Minimal subprocess.Popen stand-in driving the N3 reader-thread loop."""

    def __init__(self, lines, returncode=0):
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode if self.stdout.closed else None


class _SlowOutputFakeProcess(_FakeProcess):
    def __init__(self, lines, returncode=0):
        super().__init__(lines, returncode)
        self.stdout = _SlowFirstLineStdout(lines)


class TestRunTrackingOnNode(unittest.TestCase):
    """Covers the guard paths, happy path, cancel, failure, backtrack and refine."""

    def setUp(self):
        mock_nuke.reset_mock()
        # nuke.temp_dir() must return a real directory (used by both the pure
        # output-json resolver and tempfile.mkdtemp) or os.path.join raises.
        mock_nuke.temp_dir.return_value = tempfile.gettempdir()
        mock_nuke.root().fps.return_value = 24.0
        # ProgressTask.isCancelled() must default to False so the happy path
        # does not take the cancel branch (a bare MagicMock return_value is truthy).
        mock_nuke.ProgressTask.return_value.isCancelled.return_value = False

    def _make_node(self, **knob_values):
        """Build a mocked FaceTracker node with a real knobs dict for `in` checks."""
        knobs = {
            "start_frame": MagicMock(value=lambda: knob_values.get("start_frame", 1)),
            "end_frame": MagicMock(value=lambda: knob_values.get("end_frame", 10)),
            "refine_smartvectors": MagicMock(
                value=lambda: knob_values.get("refine_smartvectors", False)),
            "mode": MagicMock(value=lambda: knob_values.get("mode", "Image")),
            "quality": MagicMock(value=lambda: knob_values.get("quality", "Standard")),
        }
        if "backtrack" in knob_values:
            knobs["backtrack"] = MagicMock(value=lambda: knob_values["backtrack"])
        if "write_to_file" in knob_values:
            knobs["write_to_file"] = MagicMock(value=lambda: knob_values["write_to_file"])

        node = MagicMock()
        node.name.return_value = "TestTracker"
        node.knobs.return_value = knobs
        node.__getitem__.side_effect = lambda key: knobs[key]

        input_node = MagicMock()
        input_node.format().width.return_value = 1920
        input_node.format().height.return_value = 1080
        vector_node = MagicMock()
        node.input.side_effect = lambda idx: input_node if idx == 0 else vector_node
        node._input_node = input_node
        node._vector_node = vector_node
        return node

    def _patch_happy_subprocess(self, lines=None, returncode=0):
        lines = lines if lines is not None else [
            "PROGRESS: 50%",
            "PROGRESS: 100%",
            "[SUCCESS] tracking complete",
        ]
        # A factory so each Popen call gets a FRESH process (its own stdout
        # stream); a shared return_value would be drained after the first pass.
        procs = []

        def _factory(*args, **kwargs):
            proc = _FakeProcess(lines=lines, returncode=returncode)
            procs.append(proc)
            return proc

        patcher = patch("nuke_tracker.subprocess.Popen", side_effect=_factory)
        return procs, patcher

    # --- guard paths -------------------------------------------------------

    def test_no_input_node_returns_false(self):
        node = self._make_node()
        node.input.side_effect = lambda idx: None if idx == 0 else MagicMock()
        self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_refine_enabled_without_vector_node_returns_false(self):
        node = self._make_node(refine_smartvectors=True)
        node.input.side_effect = lambda idx: MagicMock() if idx == 0 else None
        self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_refine_enabled_without_vector_channels_returns_false(self):
        node = self._make_node(refine_smartvectors=True)
        with patch("nuke_tracker.find_vector_channels", return_value=(None, None)):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_start_after_end_returns_false(self):
        node = self._make_node(start_frame=20, end_frame=10)
        with patch("nuke_tracker._locate_venv_python", return_value="/fake/python"):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_venv_python_missing_returns_false(self):
        node = self._make_node()
        # Patch os.path.exists so the real _locate_venv_python reports the venv
        # missing, calls nuke.message, and returns None (rather than mocking the
        # whole helper, which would skip the message).
        with patch("nuke_tracker.os.path.exists", return_value=False):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    # --- happy / failure / cancel paths ------------------------------------

    def test_happy_path_no_backtrack_no_refine_returns_true(self):
        node = self._make_node()
        procs, popen_patch = self._patch_happy_subprocess()
        with popen_patch, patch("nuke_tracker._locate_venv_python", return_value="/fake/python"):
            result = nuke_tracker.run_tracking_on_node(node)
        self.assertTrue(result)
        # No backtrack -> exactly one backend pass (one subprocess spawn).
        self.assertEqual(len(procs), 1)

    def test_run_tracking_pass_waits_through_quiet_stdout_period(self):
        """A temporary lack of backend stdout must not be treated as EOF/failure."""
        proc = _SlowOutputFakeProcess([
            "PROGRESS: 100%",
            "[SUCCESS] tracking complete",
        ])

        with patch("nuke_tracker.subprocess.Popen", return_value=proc):
            result = nuke_tracker._run_tracking_passes(
                [{"name": "Forward", "cmd": ["python", "backend.py"], "offset": 0.0, "weight": 1.0}],
                mock_nuke.ProgressTask.return_value,
                1,
                1,
            )

        self.assertTrue(result)
        self.assertFalse(mock_nuke.message.called)

    def test_subprocess_nonzero_exit_returns_false(self):
        node = self._make_node()
        procs, popen_patch = self._patch_happy_subprocess(
            lines=["PROGRESS: 50%", "[ERROR] backend exploded"], returncode=1)
        with popen_patch, patch("nuke_tracker._locate_venv_python", return_value="/fake/python"):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_subprocess_no_success_token_returns_false(self):
        node = self._make_node()
        # returncode 0 but no [SUCCESS] line -> pass_success stays False -> failure.
        procs, popen_patch = self._patch_happy_subprocess(
            lines=["PROGRESS: 100%"], returncode=0)
        with popen_patch, patch("nuke_tracker._locate_venv_python", return_value="/fake/python"):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(mock_nuke.message.called)

    def test_cancel_terminates_subprocess_and_returns_false(self):
        node = self._make_node()
        procs, popen_patch = self._patch_happy_subprocess()
        # Make the ProgressTask report cancellation immediately.
        task = mock_nuke.ProgressTask.return_value
        task.isCancelled.return_value = True
        with popen_patch, patch("nuke_tracker._locate_venv_python", return_value="/fake/python"):
            self.assertFalse(nuke_tracker.run_tracking_on_node(node))
        self.assertTrue(procs[0].terminated)
        self.assertTrue(mock_nuke.message.called)

    # --- backtrack + refine dispatch ---------------------------------------

    def test_backtrack_runs_two_passes_and_merges(self):
        node = self._make_node(backtrack=True)
        procs, popen_patch = self._patch_happy_subprocess()
        with popen_patch, \
             patch("nuke_tracker._locate_venv_python", return_value="/fake/python"), \
             patch("nuke_tracker._merge_backtrack_passes", return_value=True) as merge_mock:
            result = nuke_tracker.run_tracking_on_node(node)
        self.assertTrue(result)
        # Two passes (forward + backward) each spawn one subprocess.
        self.assertEqual(len(procs), 2)
        self.assertTrue(merge_mock.called)

    def test_refine_dispatches_apply_smartvector_refinement(self):
        node = self._make_node(refine_smartvectors=True)
        procs, popen_patch = self._patch_happy_subprocess()
        tracker_json = '{"Nose_Tip": {"1": [1.0, 2.0]}}'
        with popen_patch, \
             patch("nuke_tracker._locate_venv_python", return_value="/fake/python"), \
             patch("nuke_tracker.find_vector_channels", return_value=("u", "v")), \
             patch("nuke_tracker.apply_smartvector_refinement", return_value=True) as refine_mock, \
             patch("builtins.open", mock_open(read_data=tracker_json)):
            result = nuke_tracker.run_tracking_on_node(node)
        self.assertTrue(result)
        self.assertTrue(refine_mock.called)


if __name__ == "__main__":
    unittest.main()
