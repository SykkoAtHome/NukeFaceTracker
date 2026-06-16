import os
import sys
import requests

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")

def download_model(dest_path=MODEL_PATH):
    """Downloads face_landmarker.task model file from Google storage if it does not exist."""
    if os.path.exists(dest_path):
        print(f"[INFO] Model file already exists at: {dest_path}")
        return True

    print(f"[INFO] Downloading MediaPipe Face Landmarker model from: {MODEL_URL}")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        response = requests.get(MODEL_URL, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 * 1024  # 1MB
        downloaded = 0

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        sys.stdout.write(f"\r[INFO] Download Progress: {percent:.1f}% ({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
                        sys.stdout.flush()
        
        sys.stdout.write("\n")
        print("[SUCCESS] Model downloaded and saved successfully!")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to download model: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False

if __name__ == "__main__":
    download_model()
