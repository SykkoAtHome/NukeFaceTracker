import os
import sys
import argparse
import json
import re

# Import landmarks configurations
import landmarks_config

def _serialize_blendshapes(categories):
    """Safely extracts blendshape category scores into a dictionary."""
    if not categories:
        return {}
    return {
        cat.category_name: round(cat.score, 4)
        for cat in categories
    }

def _load_mediapipe():
    """Lazily import OpenCV and MediaPipe.

    Kept out of the module top level so this module has no third-party imports at
    import time. This keeps Nuke's interpreter clean if it ever imports this module
    in-process (normally tracker_backend runs as an isolated subprocess). The
    subprocess resolves packages from its own venv python + sys.path[0] (this
    file's directory) and never relies on an inherited PYTHONPATH.
    """
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        return cv2, mp, python, vision
    except ImportError as e:
        print(f"[ERROR] Missing MediaPipe/OpenCV dependency: {e}")
        sys.exit(1)

def _to_nuke_xy(lm, width, height):
    """Convert a MediaPipe normalized landmark to Nuke pixel space [x, y].

    MediaPipe landmarks are normalized [0,1] with origin at top-left; Nuke
    uses pixel coordinates with origin at bottom-left, so y is flipped.
    """
    return [round(lm.x * width, 3), round(height - (lm.y * height), 3)]

from tracker_utils import (
    _avg_points,
    _avg_point,
    _merge_frame_values,
    merge_results
)

def get_frame_path(pattern, frame_num):
    """Converts a Nuke-style path pattern (e.g., .####.png or .%04d.png) to a concrete frame file path."""
    cleaned_pattern = pattern

    # Handle #### -> %04d
    if "####" in pattern:
        cleaned_pattern = pattern.replace("####", "%04d")
    else:
        # Handle custom number of hashes e.g. ### -> %03d
        hash_match = re.search(r'(#+)', pattern)
        if hash_match:
            hashes = hash_match.group(1)
            cleaned_pattern = pattern.replace(hashes, f"%0{len(hashes)}d")

    if "%" in cleaned_pattern:
        try:
            return cleaned_pattern % frame_num
        except Exception as e:
            print(f"[WARNING] Path formatting error: {e}")
    return cleaned_pattern

def run_tracking_pass(frame_sequence, options, args, is_sequence, width, height, fps, contours_to_track, landmarks_to_track, run_mode, total_progress_frames, progress_offset):
    cv2, mp, python, vision = _load_mediapipe()
    # Initialize detector for this pass
    try:
        detector = vision.FaceLandmarker.create_from_options(options)
    except Exception as e:
        print(f"[ERROR] Failed to initialize MediaPipe Face Landmarker detector: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    cap = None
    try:
        if not is_sequence:
            cap = cv2.VideoCapture(args.input)
            if not cap.isOpened():
                print(f"[ERROR] Failed to open video file: {args.input}")
                # Raise so the finally below still releases detector/cap instead
                # of bypassing cleanup via sys.exit. main() catches and exits 1.
                raise RuntimeError(f"Failed to open video file: {args.input}")

        pass_results = {}
        blendshapes_data = {}
        for group_name in contours_to_track.keys():
            pass_results[group_name] = {}
        for name in landmarks_to_track.keys():
            pass_results[name] = {}

        for idx, frame_num in enumerate(frame_sequence):
            try:
                cv_image = None

                if is_sequence:
                    frame_path = get_frame_path(args.input, frame_num)
                    if not os.path.exists(frame_path):
                        print(f"[WARNING] Frame not found: {frame_path}")
                        continue
                    # Read image (using any depth flag for floating-point file support e.g. EXR)
                    cv_image = cv2.imread(frame_path, cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
                    if cv_image is None:
                        print(f"[WARNING] Failed to read frame: {frame_path}")
                        continue

                    # If high dynamic range/bit depth (e.g. 16/32-bit float), convert to 8-bit LDR for MediaPipe
                    if cv_image.dtype != 'uint8':
                        cv2.normalize(cv_image, cv_image, 0, 255, cv2.NORM_MINMAX)
                        cv_image = cv_image.astype('uint8')
                else:
                    # Set position index (0-based) for video file.
                    # Seek by the relative enumerate index, not the user's Nuke frame
                    # number: VFX ranges often do not start at 1 (e.g. start=1001), so
                    # using frame_num directly would seek past the video end.
                    video_idx = frame_num - args.start
                    cap.set(cv2.CAP_PROP_POS_FRAMES, video_idx)
                    ret, cv_image = cap.read()
                    if not ret or cv_image is None:
                        print(f"[WARNING] Failed to read frame {frame_num} from video")
                        continue

                # Fallback resolution detection from the first loaded frame
                if not width or not height:
                    height, width = cv_image.shape[:2]
                    print(f"[INFO] Auto-detected frame resolution: {width}x{height}")

                # Convert BGR -> RGB for MediaPipe ingestion
                rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)

                # Perform inference
                if run_mode == vision.RunningMode.VIDEO:
                    # Generate a monotonic timestamp in milliseconds based on the loop index (idx).
                    # This ensures that timestamps always start exactly at 0, are strictly non-negative, and
                    # monotonically increase, even if the user tracks negative frame ranges (common in VFX)
                    # or custom non-zero start frames.
                    timestamp_ms = int(idx * 1000.0 / fps)
                    detection_result = detector.detect_for_video(mp_image, timestamp_ms)
                else:
                    detection_result = detector.detect(mp_image)

                if detection_result.face_landmarks:
                    landmarks = detection_result.face_landmarks[0]

                    if hasattr(detection_result, 'face_blendshapes') and detection_result.face_blendshapes:
                        blendshapes_data[str(frame_num)] = _serialize_blendshapes(detection_result.face_blendshapes[0])

                    # Fetch coordinates for each contour group sequentially
                    for group_name, indices in contours_to_track.items():
                        points = []
                        all_valid = True
                        for l_idx in indices:
                            if l_idx < len(landmarks):
                                lm = landmarks[l_idx]
                                points.append(_to_nuke_xy(lm, width, height))
                            else:
                                all_valid = False
                        if all_valid and len(points) == len(indices):
                            pass_results[group_name][str(frame_num)] = points

                    # Fetch coordinates for each selected landmark
                    for name, l_idx in landmarks_to_track.items():
                        if l_idx < len(landmarks):
                            lm = landmarks[l_idx]
                            # Store as string keys for strict JSON compatibility
                            pass_results[name][str(frame_num)] = _to_nuke_xy(lm, width, height)

            except Exception as frame_error:
                print(f"[WARNING] Error occurred while tracking frame {frame_num}: {frame_error}")
                import traceback
                traceback.print_exc()

            # Output progress stream for Nuke parsing
            current_progress_frame = progress_offset + idx + 1
            progress = int((current_progress_frame / total_progress_frames) * 100)
            sys.stdout.write(f"PROGRESS: {progress}%\n")
            sys.stdout.flush()

        return pass_results, blendshapes_data, width, height
    finally:
        # Always release detector and cap, even on early failure. Each is
        # guarded so an error in one does not mask the other.
        if cap:
            try:
                cap.release()
            except Exception as e:
                print(f"[WARNING] Exception during cap.release(): {e}")
        try:
            detector.close()
        except Exception as e:
            print(f"[WARNING] Exception during detector.close(): {e}")





def main():
    try:
        parser = argparse.ArgumentParser(description="MediaPipe Face Tracker Backend for Nuke MVP")
        parser.add_argument("--input", required=True, help="Path to video or image sequence (using #### or %%04d)")
        parser.add_argument("--output", required=True, help="Path to output JSON file")
        parser.add_argument("--start", type=int, required=True, help="Start frame index")
        parser.add_argument("--end", type=int, required=True, help="End frame index")
        parser.add_argument("--width", type=int, help="Optional frame width (passed from Nuke)")
        parser.add_argument("--height", type=int, help="Optional frame height (passed from Nuke)")
        parser.add_argument("--mapping", help="Path to mapping JSON exported from the landmark grouper")
        parser.add_argument("--landmarks", help="Comma-separated landmark names to track")
        parser.add_argument("--export-type", default="trackers", choices=["trackers", "roto"], help="Export type: standard trackers or sequential roto splines")
        parser.add_argument("--mode", default="video", choices=["image", "video"], help="Tracking mode: image (frame-by-frame) or video (temporal tracking)")
        parser.add_argument("--fps", type=float, default=24.0, help="Framerate for temporal tracking (video mode)")
        parser.add_argument("--min-det-confidence", type=float, default=0.5, help="Minimum face detection confidence (0.0-1.0)")
        parser.add_argument("--min-track-confidence", type=float, default=0.5, help="Minimum tracking confidence (0.0-1.0)")
        parser.add_argument("--backward", action="store_true", help="Track frames in reverse order (from end to start)")

        args = parser.parse_args()

        if args.start > args.end:
            print(f"[ERROR] Start frame ({args.start}) cannot be greater than end frame ({args.end}).")
            sys.exit(1)

        if (args.end - args.start + 1) > 1_000_000:
            print(f"[ERROR] Requested frame range ({args.start} to {args.end}) exceeds maximum allowed frames of 1,000,000.")
            sys.exit(1)

        cv2, mp, python, vision = _load_mediapipe()

        if args.mapping:
            landmarks_config.load_mapping(args.mapping)

        # Always track the full backend payload. Frontend export options decide
        # which subset is turned into Tracker4 points or Roto splines later.
        contours_to_track = dict(landmarks_config.CONTOUR_GROUPS)
        landmarks_to_track = landmarks_config.get_landmarks_for_analysis()

        # Determine the frame sequence
        if args.backward:
            frame_sequence = list(range(args.end, args.start - 1, -1))
            print(f"[INFO] Tracking reverse sequence of {len(frame_sequence)} frames from {args.end} down to {args.start}...")
        else:
            frame_sequence = list(range(args.start, args.end + 1))
            print(f"[INFO] Tracking forward sequence of {len(frame_sequence)} frames from {args.start} to {args.end}...")

        # Locate face_landmarker.task model file
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")
        if not os.path.exists(model_path):
            print(f"[ERROR] MediaPipe model file not found at: {model_path}")
            print("[INFO] Attempting to automatically download the model file...")
            import model_downloader
            if not model_downloader.download_model(model_path):
                sys.exit(1)

        # Prepare MediaPipe Face Landmarker configurations
        run_mode = vision.RunningMode.VIDEO if args.mode == "video" else vision.RunningMode.IMAGE
        print(f"[INFO] Using MediaPipe RunningMode: {run_mode.name}")

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=run_mode,
            min_face_detection_confidence=args.min_det_confidence,
            min_tracking_confidence=args.min_track_confidence,
            output_face_blendshapes=True,  # WARNING: Do NOT add Delegate.GPU here. MediaPipe bug #5576 breaks blendshapes on GPU.
            output_facial_transformation_matrixes=False,
            num_faces=1
        )

        # Detect input type (video file vs image sequence)
        is_sequence = "%" in args.input or "#" in args.input or not any(args.input.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".m4v"])

        # Resolve resolution and frame rate
        width = args.width
        height = args.height
        fps = args.fps

        if not is_sequence and (not width or not height):
            temp_cap = cv2.VideoCapture(args.input)
            try:
                if temp_cap.isOpened():
                    width = int(temp_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(temp_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    video_fps = temp_cap.get(cv2.CAP_PROP_FPS)
                    if video_fps and video_fps > 0:
                        fps = video_fps
            finally:
                temp_cap.release()

        if not fps or fps <= 0:
            fps = 24.0

        # Run tracking pass
        total_progress_frames = len(frame_sequence)
        results_data, blendshapes_data, width, height = run_tracking_pass(
            frame_sequence, options, args, is_sequence, width, height, fps,
            contours_to_track, landmarks_to_track, run_mode, total_progress_frames, 0
        )

        # Serialize results to JSON
        try:
            out_dir = os.path.dirname(args.output) or "."
            os.makedirs(out_dir, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(results_data, f, indent=2)
            
            # Serialize blendshapes to sidecar JSON if any
            if blendshapes_data:
                blendshapes_path = args.output.replace(".json", ".blendshapes.json")
                with open(blendshapes_path, "w") as f:
                    json.dump(blendshapes_data, f, indent=2)
                    
            print(f"[SUCCESS] Tracking data successfully saved to: {args.output}")
        except Exception as e:
            print(f"[ERROR] Failed to save JSON output: {e}")
            sys.exit(1)

    except Exception as e:
        import traceback
        print("[ERROR] Exception occurred during backend execution:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
