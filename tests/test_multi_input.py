import os
import sys
import json
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock, patch

# Ensure backend and frontend are in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

# Mock nuke module before importing nuke_tracker
if 'nuke' not in sys.modules:
    sys.modules['nuke'] = MagicMock()
import nuke_tracker


class MockKnob:
    def __init__(self, value, enabled=True, visible=True):
        self._value = value
        self._enabled = enabled
        self._visible = visible
        self._tool_tip = ""

    def value(self):
        return self._value

    def setValue(self, val):
        self._value = val

    def setEnabled(self, val):
        self._enabled = val

    def setVisible(self, val):
        self._visible = val

    def enabled(self):
        return self._enabled

    def visible(self):
        return self._visible

    def setFlag(self, flag):
        pass

    def setTooltip(self, tip):
        self._tool_tip = tip


class MockNode:
    def __init__(self, name="FaceTracker1", knobs_dict=None):
        self._name = name
        self._inputs = []
        self._knobs = knobs_dict or {}

    def Class(self):
        return "Group"

    def name(self):
        return self._name

    def knobs(self):
        return self._knobs

    def knob(self, name):
        return self._knobs.get(name)

    def __getitem__(self, name):
        if name not in self._knobs:
            raise KeyError(name)
        return self._knobs[name]

    def inputs(self):
        return len(self._inputs)

    def input(self, idx):
        if 0 <= idx < len(self._inputs):
            return self._inputs[idx]
        return None

    def setInput(self, idx, node):
        while len(self._inputs) <= idx:
            self._inputs.append(None)
        self._inputs[idx] = node


class TestMultiInput(unittest.TestCase):
    
    def test_resolve_output_json_path_temp(self):
        """Test that _resolve_output_json_path adds correct target suffix for temp paths."""
        mock_node = MagicMock()
        mock_node.name.return_value = "FaceTracker1"
        
        # Scenario 1: write_to_file is False, track_target is 'source'
        mock_node.__getitem__.side_effect = lambda key: MagicMock(value=lambda: False) if key == 'write_to_file' else MagicMock(value=lambda: 'source')
        mock_node.knobs.return_value = ['write_to_file', 'track_target']
        
        with patch.dict(os.environ, {"NUKE_TEMP_DIR": "/tmp/nuke"}):
            path = nuke_tracker._resolve_output_json_path(mock_node)
            self.assertEqual(path, "/tmp/nuke/facetracker/FaceTracker1_source_data.json")

        # Scenario 2: write_to_file is False, track_target is 'expression'
        mock_node.__getitem__.side_effect = lambda key: MagicMock(value=lambda: False) if key == 'write_to_file' else MagicMock(value=lambda: 'expression')
        with patch.dict(os.environ, {"NUKE_TEMP_DIR": "/tmp/nuke"}):
            path = nuke_tracker._resolve_output_json_path(mock_node)
            self.assertEqual(path, "/tmp/nuke/facetracker/FaceTracker1_expression_data.json")

    def test_resolve_output_json_path_custom(self):
        """Test that _resolve_output_json_path appends and swaps target suffixes for custom paths."""
        mock_node = MagicMock()
        mock_node.name.return_value = "FaceTracker1"
        mock_node.knobs.return_value = ['write_to_file', 'track_target', 'output_json']
        
        # Helper to setup node knob values
        def setup_knobs(write_to_file, track_target, output_json):
            def side_effect(key):
                if key == 'write_to_file':
                    return MagicMock(value=lambda: write_to_file)
                elif key == 'track_target':
                    return MagicMock(value=lambda: track_target)
                elif key == 'output_json':
                    return MagicMock(value=lambda: output_json)
                raise KeyError(key)
            mock_node.__getitem__.side_effect = side_effect

        # Scenario 1: custom path without suffix, target = 'source'
        setup_knobs(True, 'source', 'C:/data/shot01.json')
        path = nuke_tracker._resolve_output_json_path(mock_node)
        self.assertEqual(path, 'C:/data/shot01_source_data.json')

        # Scenario 2: custom path with '_source_data' suffix, target = 'expression' (should swap to '_expression_data')
        setup_knobs(True, 'expression', 'C:/data/shot01_source_data.json')
        path = nuke_tracker._resolve_output_json_path(mock_node)
        self.assertEqual(path, 'C:/data/shot01_expression_data.json')

        # Scenario 3: custom path with '_expression_data' suffix, target = 'source' (should swap to '_source_data')
        setup_knobs(True, 'source', 'C:/data/shot01_expression_data.json')
        path = nuke_tracker._resolve_output_json_path(mock_node)
        self.assertEqual(path, 'C:/data/shot01_source_data.json')

    def test_find_upstream_read_ignores_port_2(self):
        """Test that find_upstream_read ignores port 2 when the node is a FaceTracker group."""
        mock_tracker = MagicMock()
        mock_tracker.Class.return_value = "Group"
        mock_tracker.name.return_value = "FaceTracker1"
        mock_tracker.inputs.return_value = 3
        mock_tracker.knob.return_value = None  # no 'file' knob
        mock_tracker.knobs.return_value = {'track_target': MagicMock()}
        
        # Inputs connected to tracker:
        mock_input_0 = MagicMock()  # port 0
        mock_input_1 = MagicMock()  # port 1 (SmartVector)
        mock_input_2 = MagicMock()  # port 2 (Expression_Face)
        
        # Setup find_upstream_read mock results
        read_node_0 = MagicMock()
        read_node_0.knob.side_effect = lambda name: MagicMock() if name == 'file' else None
        read_node_0.name.return_value = "Read_Source"
        
        read_node_2 = MagicMock()
        read_node_2.knob.side_effect = lambda name: MagicMock() if name == 'file' else None
        read_node_2.name.return_value = "Read_Expr"
        
        mock_input_0.knob.return_value = None
        mock_input_0.inputs.return_value = 1
        mock_input_0.input.return_value = read_node_0
        
        mock_input_2.knob.return_value = None
        mock_input_2.inputs.return_value = 1
        mock_input_2.input.return_value = read_node_2
        
        # When querying inputs of mock_tracker
        def tracker_input(idx):
            if idx == 0:
                return mock_input_0
            elif idx == 1:
                return None
            elif idx == 2:
                return mock_input_2
            return None
        mock_tracker.input.side_effect = tracker_input
        
        # Run find_upstream_read with input 0 connected (should return read_node_0)
        res = nuke_tracker.find_upstream_read(mock_tracker)
        self.assertEqual(res, read_node_0)
        
        # Now disconnect input 0 (should skip input 2 even though connected, returning None)
        mock_tracker.input.side_effect = lambda idx: None if idx == 0 else tracker_input(idx)
        res = nuke_tracker.find_upstream_read(mock_tracker)
        self.assertIsNone(res)

    def test_resolve_target_input_node(self):
        """Test _resolve_target_input_node returns correct ports for target."""
        node = MockNode()
        input_0 = MockNode("SourceNode")
        input_2 = MockNode("ExpressionNode")
        node.setInput(0, input_0)
        node.setInput(2, input_2)

        # target = 'source' -> should return input(0)
        self.assertEqual(nuke_tracker._resolve_target_input_node(node, 'source'), input_0)

        # target = 'expression' -> should return input(2)
        self.assertEqual(nuke_tracker._resolve_target_input_node(node, 'expression'), input_2)

        # target = None, track_target knob is 'source'
        node._knobs['track_target'] = MockKnob('source')
        self.assertEqual(nuke_tracker._resolve_target_input_node(node, None), input_0)

        # target = None, track_target knob is 'expression'
        node._knobs['track_target'] = MockKnob('expression')
        self.assertEqual(nuke_tracker._resolve_target_input_node(node, None), input_2)

    def test_set_range_to_input(self):
        """Test set_range_to_input updates frames from the correct input node."""
        node = MockNode()
        node._knobs['start_frame'] = MockKnob(1)
        node._knobs['end_frame'] = MockKnob(100)
        node._knobs['track_target'] = MockKnob('source')

        input_0 = MockNode("SourceNode")
        input_0.firstFrame = lambda: 10
        input_0.lastFrame = lambda: 50

        input_2 = MockNode("ExpressionNode")
        input_2.firstFrame = lambda: 100
        input_2.lastFrame = lambda: 200

        node.setInput(0, input_0)
        node.setInput(2, input_2)

        # Case 1: Target is source
        nuke_tracker.set_range_to_input(node)
        self.assertEqual(node['start_frame'].value(), 10)
        self.assertEqual(node['end_frame'].value(), 50)

        # Case 2: Target is expression
        node['track_target'].setValue('expression')
        nuke_tracker.set_range_to_input(node)
        self.assertEqual(node['start_frame'].value(), 100)
        self.assertEqual(node['end_frame'].value(), 200)

    def test_set_range_to_input_missing_expression(self):
        """Test set_range_to_input shows a message when expression input is missing."""
        import nuke
        nuke.message.reset_mock()
        node = MockNode()
        node._knobs['start_frame'] = MockKnob(1)
        node._knobs['end_frame'] = MockKnob(100)
        node._knobs['track_target'] = MockKnob('expression')
        
        # input(2) is None
        nuke_tracker.set_range_to_input(node)
        nuke.message.assert_called_with("No input node connected to the 'Expression_Face' input (port 2).")

    @patch('nuke_tracker._configure_mapping_for_node', return_value=True)
    @patch('nuke_tracker.get_names_to_track_for_analysis', return_value=['jaw'])
    def test_validate_tracking_inputs_defensive_guard(self, mock_get_names, mock_config):
        """Test that _validate_tracking_inputs disables refine_smartvectors for expression target."""
        import nuke
        nuke.message.reset_mock()
        node = MockNode()
        node._knobs['track_target'] = MockKnob('expression')
        node._knobs['refine_smartvectors'] = MockKnob(True)
        node._knobs['backtrack'] = MockKnob(False)
        node._knobs['start_frame'] = MockKnob(10)
        node._knobs['end_frame'] = MockKnob(20)
        node._knobs['write_to_file'] = MockKnob(False)
        
        # Set inputs
        input_2 = MockNode("ExpressionNode")
        input_2.format = lambda: MagicMock(width=lambda: 1920, height=lambda: 1080)
        node.setInput(2, input_2)

        # Run validation
        params = nuke_tracker._validate_tracking_inputs(node)
        
        # Verify defensive guard did its job
        self.assertFalse(node['refine_smartvectors'].value())
        nuke.message.assert_any_call("SmartVector refinement is not supported when tracking the expression target.\nDisabling refinement.")
        self.assertIsNotNone(params)

    def test_visibility_callbacks(self):
        """Test update_track_target_visibility and update_knob_visibility_on_target_change."""
        node = MockNode()
        node._knobs['track_target'] = MockKnob('expression', visible=True)
        node._knobs['refine_smartvectors'] = MockKnob(True, enabled=True)
        node._knobs['write_to_file'] = MockKnob(False)
        node._knobs['anchor_stiffness'] = MockKnob(0.5, visible=True)

        # Connect port 2
        input_2 = MockNode("ExpressionNode")
        node.setInput(2, input_2)

        # Case 1: port 2 connected, track_target set to expression
        nuke_tracker.update_track_target_visibility(node)
        self.assertTrue(node['track_target'].visible())
        self.assertEqual(node['track_target'].value(), 'expression')
        # Since target is expression, refine_smartvectors should be disabled and False
        self.assertFalse(node['refine_smartvectors'].value())
        self.assertFalse(node['refine_smartvectors'].enabled())

        # Case 2: port 2 disconnected
        node['track_target'].setValue('expression')
        node['refine_smartvectors'].setValue(True)
        node['refine_smartvectors'].setEnabled(True)
        node.setInput(2, None) # disconnect port 2

        nuke_tracker.update_track_target_visibility(node)
        # Should hide track_target and force value to 'source'
        self.assertFalse(node['track_target'].visible())
        self.assertEqual(node['track_target'].value(), 'source')
        # Since target is now source, refine_smartvectors should be enabled
        self.assertTrue(node['refine_smartvectors'].enabled())

    @patch('nuke_tracker._configure_mapping_for_node', return_value=True)
    @patch('nuke_tracker.get_names_to_track_for_analysis', return_value=['jaw'])
    def test_e2e_multi_input_flow(self, mock_get_names, mock_config):
        """Test the comprehensive E2E multi-input flow."""
        import nuke
        nuke.message.reset_mock()
        node = MockNode()
        node._knobs['track_target'] = MockKnob('source', visible=True)
        node._knobs['refine_smartvectors'] = MockKnob(True, enabled=True)
        node._knobs['anchor_stiffness'] = MockKnob(0.5, visible=True)
        node._knobs['write_to_file'] = MockKnob(False)
        node._knobs['start_frame'] = MockKnob(1)
        node._knobs['end_frame'] = MockKnob(10)

        input_0 = MockNode("SourceNode")
        input_0.format = lambda: MagicMock(width=lambda: 1920, height=lambda: 1080)
        node.setInput(0, input_0)

        # 1. Initially port 2 disconnected
        nuke_tracker.update_track_target_visibility(node)
        self.assertFalse(node['track_target'].visible())
        self.assertEqual(node['track_target'].value(), 'source')
        path = nuke_tracker._resolve_output_json_path(node)
        self.assertTrue(path.endswith('_source_data.json'))

        # 2. Connect port 2
        input_2 = MockNode("ExpressionNode")
        input_2.format = lambda: MagicMock(width=lambda: 1280, height=lambda: 720)
        node.setInput(2, input_2)

        nuke_tracker.update_track_target_visibility(node)
        self.assertTrue(node['track_target'].visible())

        # 3. Change target to expression
        node['track_target'].setValue('expression')
        nuke_tracker.update_knob_visibility_on_target_change(node)
        path2 = nuke_tracker._resolve_output_json_path(node)
        self.assertTrue(path2.endswith('_expression_data.json'))

        # Also, refine_smartvectors should be disabled and set to False
        self.assertFalse(node['refine_smartvectors'].value())
        self.assertFalse(node['refine_smartvectors'].enabled())

        # 4. Try running validation on expression target
        # Simulate someone bypassing UI and setting refine_smartvectors=True
        node['refine_smartvectors'].setValue(True)
        params = nuke_tracker._validate_tracking_inputs(node)

        # Defensive guard must reset it and warn
        self.assertFalse(node['refine_smartvectors'].value())
        nuke.message.assert_any_call("SmartVector refinement is not supported when tracking the expression target.\nDisabling refinement.")

        # Check format resolution (should be input_2 format, not input_0 format)
        width, height = nuke_tracker._resolve_input_dimensions(node, 'expression')
        self.assertEqual(width, 1280)
        self.assertEqual(height, 720)

if __name__ == '__main__':
    unittest.main()
