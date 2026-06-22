import hashlib
import hmac
import os
import sys
from urllib.parse import urlparse, urljoin

import requests

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")

# SHA-256 digest the model file must match before it is trusted. Pinned from the
# official Google MediaPipe storage bucket (MODEL_URL) over HTTPS so a tampered or
# truncated file on disk is detected on every run (closes the TOCTOU / no-checksum
# gap). Update this if the upstream model version is intentionally changed.
EXPECTED_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

# Hard cap on downloaded model size. face_landmarker.task is ~10 MB, so 60 MB
# gives comfortable headroom while rejecting runaway / misdirected responses.
MAX_MODEL_BYTES = 60 * 1024 * 1024


def _sha256_of_file(path):
    """Compute the sha256 hex digest of a file, reading in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_model_hash(path):
    """Return True if EXPECTED_MODEL_SHA256 is empty (not pinned) or matches the file."""
    if not EXPECTED_MODEL_SHA256:
        return True
    try:
        digest = _sha256_of_file(path)
    except OSError:
        return False
    return hmac.compare_digest(digest, EXPECTED_MODEL_SHA256)


def _download_to_part(response, part_path):
    """Stream the response body into part_path with a size cap.

    Returns True on a complete, in-cap download, False on size violation.
    On violation the partial file is removed before returning.
    """
    try:
        total_size = int(response.headers.get("content-length", 0))
    except (TypeError, ValueError):
        total_size = 0

    if 0 < total_size > MAX_MODEL_BYTES:
        print(f"\n[ERROR] Model size {total_size} bytes exceeds cap {MAX_MODEL_BYTES} bytes; aborting.")
        return False

    block_size = 1024 * 1024  # 1MB
    downloaded = 0
    exceeded = False

    with open(part_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=block_size):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            if downloaded > MAX_MODEL_BYTES:
                exceeded = True
                break
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                sys.stdout.write(f"\r[INFO] Download Progress: {percent:.1f}% ({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
                sys.stdout.flush()

    if exceeded:
        print(f"\n[ERROR] Download exceeded cap {MAX_MODEL_BYTES} bytes; aborting.")
        if os.path.exists(part_path):
            os.remove(part_path)
        return False

    return True


def download_model(dest_path=MODEL_PATH):
    """Downloads face_landmarker.task model file from Google storage if it does not exist.

    Returns True on success / existing valid file, False on failure. Errors are
    printed to stdout (existing behavior).
    """
    if os.path.exists(dest_path):
        if _verify_model_hash(dest_path):
            print(f"[INFO] Model file already exists at: {dest_path}")
            return True
        print(f"[INFO] Existing model file at {dest_path} failed hash verification; re-downloading.")
        try:
            os.remove(dest_path)
        except OSError as e:
            print(f"[ERROR] Could not remove invalid model file: {e}")
            return False

    print(f"[INFO] Downloading MediaPipe Face Landmarker model from: {MODEL_URL}")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    part_path = dest_path + ".part"

    try:
        url = MODEL_URL
        model_host = urlparse(MODEL_URL).hostname
        # Follow up to 5 redirects manually so each Location host can be
        # validated against the original MODEL_URL origin.
        for _ in range(6):
            response = requests.get(url, stream=True, timeout=(10, 300), allow_redirects=False)
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    print("\n[ERROR] Redirect response missing Location header.")
                    return False
                resolved_location = urljoin(url, location)
                parsed_location = urlparse(resolved_location)
                if parsed_location.hostname != model_host:
                    print(f"\n[ERROR] Redirect target host '{parsed_location.hostname}' does not match model host '{model_host}'.")
                    return False
                if parsed_location.scheme != "https":
                    print(f"\n[ERROR] Redirect target scheme '{parsed_location.scheme}' is not secure (HTTPS required).")
                    return False
                url = resolved_location
                continue
            # Non-redirect response: stream to the .part file. The context
            # manager ensures the connection closes on both success and failure.
            with response:
                response.raise_for_status()
                if not _download_to_part(response, part_path):
                    return False
            break
        else:
            print("\n[ERROR] Too many redirects while downloading the model.")
            if os.path.exists(part_path):
                os.remove(part_path)
            return False

        # Verify the freshly downloaded file before promoting it atomically.
        if not _verify_model_hash(part_path):
            print("\n[ERROR] Downloaded model file failed hash verification.")
            if os.path.exists(part_path):
                os.remove(part_path)
            return False

        os.replace(part_path, dest_path)
        sys.stdout.write("\n")
        print("[SUCCESS] Model downloaded and saved successfully!")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to download model: {e}")
        if os.path.exists(part_path):
            os.remove(part_path)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


if __name__ == "__main__":
    download_model()