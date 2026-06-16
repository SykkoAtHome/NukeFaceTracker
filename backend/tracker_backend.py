import os
import sys
import argparse
import json
import re
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Import landmarks configurations
import landmarks_config

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

def main():
    parser = argparse.ArgumentParser(description="MediaPipe Face Tracker Backend for Nuke MVP")
    parser.add_argument("--input", required=True, help="Path to video or image sequence (using #### or %%04d)")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    parser.add_argument("--start", type=int, required=True, help="Start frame index")
    parser.add_argument("--end", type=int, required=True, help="End frame index")
    parser.add_argument("--width", type=int, help="Optional frame width (passed from Nuke)")
    parser.add_argument("--height", type=int, help="Optional frame height (passed from Nuke)")
    parser.add_argument("--landmarks", help="Comma-separated landmark names to track")
    parser.add_argument("--export-type", default="trackers", choices=["trackers", "roto"], help="Export type: standard trackers or sequential roto splines")
    parser.add_argument("--mode", default="video", choices=["image", "video"], help="Tracking mode: image (frame-by-frame) or video (temporal tracking)")
    parser.add_argument("--fps", type=float, default=24.0, help="Framerate for temporal tracking (video mode)")
    parser.add_argument("--min-det-confidence", type=float, default=0.5, help="Minimum face detection confidence (0.0-1.0)")
    parser.add_argument("--min-track-confidence", type=float, default=0.5, help="Minimum tracking confidence (0.0-1.0)")
    
    args = parser.parse_args()
    
    # Resolve selected landmarks or contour groups to track
    if args.export_type == "roto":
        selected_contour_names = []
        if args.landmarks:
            selected_contour_names = [name.strip() for name in args.landmarks.split(",") if name.strip()]
        contours_to_track = landmarks_config.get_contour_groups_by_names(selected_contour_names)
        print(f"[INFO] Initializing roto tracking of {len(contours_to_track)} contour groups for frames {args.start}-{args.end}...")
    else:
        selected_landmark_names = []
        if args.landmarks:
            selected_landmark_names = [name.strip() for name in args.landmarks.split(",") if name.strip()]
        landmarks_to_track = landmarks_config.get_landmarks_by_names(selected_landmark_names)
        print(f"[INFO] Initializing tracking of {len(landmarks_to_track)} landmarks for frames {args.start}-{args.end}...")
    
    # Locate face_landmarker.task model file
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")
    if not os.path.exists(model_path):
        print(f"[ERROR] MediaPipe model file not found at: {model_path}")
        print("[INFO] Attempting to automatically download the model file...")
        import model_downloader
        if not model_downloader.download_model(model_path):
            sys.exit(1)
            
    # Initialize MediaPipe Face Landmarker
    try:
        run_mode = vision.RunningMode.VIDEO if args.mode == "video" else vision.RunningMode.IMAGE
        print(f"[INFO] Using MediaPipe RunningMode: {run_mode.name}")
        
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=run_mode,
            min_face_detection_confidence=args.min_det_confidence,
            min_tracking_confidence=args.min_track_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        detector = vision.FaceLandmarker.create_from_options(options)
    except Exception as e:
        print(f"[ERROR] Failed to initialize MediaPipe Face Landmarker detector: {e}")
        sys.exit(1)
        
    # Prepare results storage structure
    if args.export_type == "roto":
        results_data = {group_name: {} for group_name in contours_to_track.keys()}
    else:
        results_data = {name: {} for name in landmarks_to_track.keys()}
    
    # Detect input type (video file vs image sequence)
    is_sequence = "%" in args.input or "#" in args.input or not any(args.input.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".m4v"])
    
    cap = None
    if not is_sequence:
        cap = cv2.VideoCapture(args.input)
        if not cap.isOpened():
            print(f"[ERROR] Failed to open video file: {args.input}")
            sys.exit(1)
            
    # Resolve resolution and frame rate
    width = args.width
    height = args.height
    
    fps = args.fps
    if not is_sequence and cap:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps and video_fps > 0:
            fps = video_fps
            
    if not fps or fps <= 0:
        fps = 24.0
        
    if (not width or not height) and cap:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
    # Loop over frame range
    total_frames = args.end - args.start + 1
    
    for idx, frame_num in enumerate(range(args.start, args.end + 1)):
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
            # Set position index (0-based) for video file
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num - 1)
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
            
            if args.export_type == "roto":
                # Fetch coordinates for each contour group sequentially
                for group_name, indices in contours_to_track.items():
                    points = []
                    all_valid = True
                    for l_idx in indices:
                        if l_idx < len(landmarks):
                            lm = landmarks[l_idx]
                            x_nuke = lm.x * width
                            y_nuke = height - (lm.y * height)
                            points.append([round(x_nuke, 3), round(y_nuke, 3)])
                        else:
                            all_valid = False
                    if all_valid and len(points) == len(indices):
                        results_data[group_name][str(frame_num)] = points
            else:
                # Fetch coordinates for each selected landmark
                for name, l_idx in landmarks_to_track.items():
                    if l_idx < len(landmarks):
                        lm = landmarks[l_idx]
                        
                        # Convert coordinates to Nuke space
                        # MediaPipe: X: [0, 1] (left to right), Y: [0, 1] (top to bottom)
                        # Nuke: X: pixels (left to right), Y: pixels (bottom to top)
                        x_nuke = lm.x * width
                        y_nuke = height - (lm.y * height)
                        
                        # Store as string keys for strict JSON compatibility
                        results_data[name][str(frame_num)] = [round(x_nuke, 3), round(y_nuke, 3)]
                    
        # Output progress stream for Nuke parsing
        progress = int(((idx + 1) / total_frames) * 100)
        sys.stdout.write(f"PROGRESS: {progress}%\n")
        sys.stdout.flush()
        
    if cap:
        cap.release()
        
    # Serialize results to JSON
    try:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results_data, f, indent=2)
        print(f"[SUCCESS] Tracking data successfully saved to: {args.output}")
    except Exception as e:
        print(f"[ERROR] Failed to save JSON output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
