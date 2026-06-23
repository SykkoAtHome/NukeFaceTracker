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
        self.assertEqual(path, 'C:/data/shot01_source.json')

        # Scenario 2: custom path with '_source' suffix, target = 'expression' (should swap to '_expression')
        setup_knobs(True, 'expression', 'C:/data/shot01_source.json')
        path = nuke_tracker._resolve_output_json_path(mock_node)
        self.assertEqual(path, 'C:/data/shot01_expression.json')

        # Scenario 3: custom path with '_expression' suffix, target = 'source' (should swap to '_source')
        setup_knobs(True, 'source', 'C:/data/shot01_expression.json')
        path = nuke_tracker._resolve_output_json_path(mock_node)
        self.assertEqual(path, 'C:/data/shot01_source.json')

    def test_find_upstream_read_ignores_port_2(self):
        """Test that find_upstream_read ignores port 2 when the node is a FaceTracker group."""
        mock_tracker = MagicMock()
        mock_tracker.Class.return_value = "Group"
        mock_tracker.name.return_value = "FaceTracker1"
        mock_tracker.inputs.return_value = 3
        mock_tracker.knob.return_value = None  # no 'file' knob
        
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

if __name__ == '__main__':
    unittest.main()
