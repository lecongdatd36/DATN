"""Download OpenCV Zoo model weights, verify SHA-256, then atomically publish.

No Django import, database access, employee images, or credentials required.
"""
import argparse
import hashlib
from pathlib import Path
import tempfile
import urllib.request

MODELS = {
    "face_detection_yunet_2023mar.onnx": ("face_detection_yunet", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": ("face_recognition_sface", "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/attendance/models")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    for name, (folder, checksum) in MODELS.items():
        target = args.root / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == checksum:
            print(f"Verified: {name}")
            continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{name}"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=args.root, suffix=".download", delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(url, timeout=60) as response:
                    total = 0
                    while chunk := response.read(1024*1024):
                        total += len(chunk)
                        if total > 45_000_000:
                            raise RuntimeError("Unexpected model size")
                        output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
                raise RuntimeError(f"SHA-256 mismatch: {name}")
            temporary.replace(target)
            print(f"Downloaded and verified: {name}")
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


if __name__ == "__main__":
    main()
