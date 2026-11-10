"""CPU YuNet/SFace inference. Camera images are decoded in memory and never saved.

Random head turns provide only a basic active challenge, not certified PAD/liveness.
"""
import base64
import binascii
from functools import lru_cache
import hashlib
import io
import math
from pathlib import Path
import threading

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MODEL_VERSION = "sface-2021dec-v1"
MODELS = {
    "face_detection_yunet_2023mar.onnx": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "face_recognition_sface_2021dec.onnx": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}
_inference_lock = threading.Lock()


@lru_cache(maxsize=1)
def engine():
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise ValidationError("Máy chủ chưa cài bộ nhận diện. Xem hướng dẫn ca làm/chấm công.") from None
    root = Path(settings.ATTENDANCE_MODEL_ROOT)
    for name, expected in MODELS.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValidationError("Mô hình nhận diện chưa có hoặc sai checksum. Hãy chạy setup_attendance_models.py.")
    try:
        cv2.setNumThreads(1)
        detector = cv2.FaceDetectorYN.create(str(root / "face_detection_yunet_2023mar.onnx"), "", (640, 480), 0.9, 0.3, 5000)
        recognizer = cv2.FaceRecognizerSF.create(str(root / "face_recognition_sface_2021dec.onnx"), "")
    except cv2.error:
        raise ValidationError("Không nạp được mô hình nhận diện trên máy chủ.") from None
    return cv2, np, detector, recognizer


def readiness():
    try:
        engine()
        return "", True
    except ValidationError as error:
        return " ".join(error.messages), False


def normalize(vector):
    if not isinstance(vector, list) or len(vector) != 128 or any(type(x) not in (float, int) or not math.isfinite(x) for x in vector):
        raise ValidationError("Mẫu khuôn mặt không hợp lệ.")
    length = math.sqrt(sum(x*x for x in vector))
    if length < 1e-8:
        raise ValidationError("Mẫu khuôn mặt không hợp lệ.")
    return [float(x / length) for x in vector]


def cosine(first, second):
    return sum(a*b for a, b in zip(normalize(first), normalize(second)))


def best_match(vector, profiles, threshold=None, margin=None):
    threshold = settings.ATTENDANCE_FACE_THRESHOLD if threshold is None else threshold
    margin = settings.ATTENDANCE_FACE_MARGIN if margin is None else margin
    scores = []
    for profile in profiles:
        if profile.model_version != MODEL_VERSION or not profile.embeddings:
            continue
        try:
            score = max(cosine(vector, sample) for sample in profile.embeddings)
        except ValidationError:
            continue
        scores.append((profile, score))
    scores.sort(key=lambda entry: entry[1], reverse=True)
    if not scores or scores[0][1] < threshold:
        return None
    if len(scores) > 1 and scores[0][1] - scores[1][1] < margin:
        return None
    return scores[0]


def pose_matches(yaw, pose, baseline=None):
    if not math.isfinite(yaw):
        return False
    # Calibrate the head turn against this person's initial face position.
    # Absolute nose/eye geometry differs across faces and camera positions.
    if baseline is None:
        return pose == "CENTER" and abs(yaw) <= 0.35
    delta = yaw - baseline
    return {"CENTER": abs(delta) <= 0.09, "LEFT": delta <= -0.12, "RIGHT": delta >= 0.12}.get(pose, False)


def pose_feedback(yaw, pose, baseline=None):
    instructions = {"CENTER": "Nhìn thẳng vào camera", "LEFT": "Quay nhẹ mặt sang phải của bạn", "RIGHT": "Quay nhẹ mặt sang trái của bạn"}
    instruction = instructions.get(pose, "Nhìn camera")
    movement = 0
    if baseline is not None and pose in ("LEFT", "RIGHT"):
        directed = (yaw-baseline) * (-1 if pose == "LEFT" else 1)
        movement = min(1, max(0, directed / 0.12))
        if directed < -0.04:
            instruction = "Bạn đang quay ngược hướng. " + instruction
        elif directed < 0.12:
            instruction += ", thêm một chút rồi giữ yên"
    elif baseline is not None:
        movement = min(1, max(0, 1-abs(yaw-baseline)/0.25))
    return {"pose": pose, "instruction": instruction, "movement": round(movement, 2)}


def extract_frame(encoded):
    if not isinstance(encoded, str) or not encoded.startswith("data:image/jpeg;base64,") or len(encoded) > 650000:
        raise ValidationError("Ảnh camera không hợp lệ hoặc quá lớn (tối đa 480 KB).")
    try:
        raw = base64.b64decode(encoded.split(",", 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "JPEG" or not 160 <= image.width <= 1280 or not 160 <= image.height <= 960:
                raise ValidationError("Ảnh phải là JPEG từ 160 đến 1280×960 pixel.")
            rgb = ImageOps.exif_transpose(image).convert("RGB")
    except (binascii.Error, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValidationError("Không đọc được ảnh camera.") from None
    cv2, np, detector, recognizer = engine()
    image = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    height, width = image.shape[:2]
    with _inference_lock:
        try:
            detector.setInputSize((width, height))
            _, faces = detector.detect(image)
            if faces is None or len(faces) != 1:
                raise ValidationError("Chỉ một người đứng trước camera, mặt rõ và đủ sáng.")
            face = faces[0]
            x, y, w, h = (int(value) for value in face[:4])
            if min(w, h) < 85 or x < 0 or y < 0 or x+w > width or y+h > height:
                raise ValidationError("Đứng gần hơn và đưa toàn bộ khuôn mặt vào khung.")
            crop = cv2.cvtColor(image[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            if not 35 <= float(crop.mean()) <= 230 or cv2.Laplacian(crop, cv2.CV_64F).var() < 25:
                raise ValidationError("Ảnh mờ hoặc thiếu/thừa sáng. Giữ yên và điều chỉnh ánh sáng.")
            eyes_mid = (face[4] + face[6]) / 2
            eye_distance = abs(float(face[6] - face[4]))
            yaw = float((face[8] - eyes_mid) / max(eye_distance, 1))
            aligned = recognizer.alignCrop(image, face)
            vector = recognizer.feature(aligned).flatten().astype(float).tolist()
        except cv2.error:
            raise ValidationError("Chưa xử lý được khuôn mặt. Hãy nhìn camera và thử lại.") from None
    return {"vector": normalize(vector), "yaw": yaw, "hash": hashlib.sha256(raw).hexdigest()}
