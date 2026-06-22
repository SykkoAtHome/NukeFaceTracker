import os
import sys

def _avg_points(f_val, b_val):
    """Average two equal-length point lists coordinate-wise.

    Preserves the existing zip(f_val, b_val) silent-truncation behavior: if the
    lists differ in length, the trailing elements of the longer list are
    silently dropped. Do not change this; a dedicated test documents it.
    """
    merged_pts = []
    for p1, p2 in zip(f_val, b_val):
        merged_pts.append([
            round((p1[0] + p2[0]) / 2.0, 3),
            round((p1[1] + p2[1]) / 2.0, 3)
        ])
    return merged_pts

def _avg_point(f_val, b_val):
    """Average two single [x, y] points coordinate-wise."""
    return [
        round((f_val[0] + b_val[0]) / 2.0, 3),
        round((f_val[1] + b_val[1]) / 2.0, 3)
    ]

def _merge_frame_values(f_frames, b_frames, average_fn):
    """Merge per-frame values from forward and backward passes.

    Frames present in both passes are combined via average_fn(f_val, b_val);
    frames present in only one pass keep that pass's value unchanged.
    """
    merged = {}
    all_frames = set(f_frames.keys()).union(b_frames.keys())
    for frame in all_frames:
        f_val = f_frames.get(frame)
        b_val = b_frames.get(frame)
        if f_val is not None and b_val is not None:
            merged[frame] = average_fn(f_val, b_val)
        elif f_val is not None:
            merged[frame] = f_val
        elif b_val is not None:
            merged[frame] = b_val
    return merged

def merge_results(forward_results, backward_results, contours_to_track, landmarks_to_track):
    merged = {}

    # Process contour groups (point-list averaging)
    for group_name in contours_to_track.keys():
        merged[group_name] = _merge_frame_values(
            forward_results.get(group_name, {}),
            backward_results.get(group_name, {}),
            _avg_points
        )

    # Process individual landmarks (single-point averaging)
    for name in landmarks_to_track.keys():
        merged[name] = _merge_frame_values(
            forward_results.get(name, {}),
            backward_results.get(name, {}),
            _avg_point
        )

    return merged
