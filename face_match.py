import tempfile
from pathlib import Path

import cv2
from deepface import DeepFace


FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
PROFILE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')


def _largest_box(boxes):
    if len(boxes) == 0:
        return None
    return max(boxes, key=lambda box: box[2] * box[3])


def _detect_face_box(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    candidates = []
    settings = [
        dict(scaleFactor=1.05, minNeighbors=3, minSize=(20, 20)),
        dict(scaleFactor=1.08, minNeighbors=4, minSize=(30, 30)),
        dict(scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)),
    ]

    for params in settings:
        faces = FACE_CASCADE.detectMultiScale(gray, **params)
        candidates.extend(faces.tolist())

    for flipped in (False, True):
        target = cv2.flip(gray, 1) if flipped else gray
        profiles = PROFILE_CASCADE.detectMultiScale(target, scaleFactor=1.08, minNeighbors=3, minSize=(20, 20))
        for x, y, w, h in profiles:
            if flipped:
                x = gray.shape[1] - x - w
            candidates.append([x, y, w, h])

    return _largest_box(candidates)


def _crop_face_to_temp(image_path, label):
    image = cv2.imread(image_path)
    if image is None:
        return None

    box = _detect_face_box(image)
    if box is None:
        return None

    x, y, w, h = box
    pad = int(max(w, h) * 0.45)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(image.shape[1], x + w + pad)
    y2 = min(image.shape[0], y + h + pad)
    crop = image[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=f'_{label}_face.jpg')
    temp.close()
    cv2.imwrite(temp.name, crop)
    return temp.name


def _verify_pair(doc_candidate, live_candidate):
    result = DeepFace.verify(
        img1_path=doc_candidate,
        img2_path=live_candidate,
        detector_backend='opencv',
        enforce_detection=False,
    )
    distance = float(result.get('distance', 1.0))
    threshold = float(result.get('threshold', 0.35))
    verified = bool(result.get('verified', False))
    return verified or distance <= threshold, distance, threshold


def match_faces(doc, live):
    temp_paths = []
    try:
        doc_crop = _crop_face_to_temp(doc, 'doc')
        live_crop = _crop_face_to_temp(live, 'live')
        temp_paths.extend(path for path in (doc_crop, live_crop) if path)

        doc_candidates = [path for path in (doc_crop, doc) if path]
        live_candidates = [path for path in (live_crop, live) if path]
        best_distance = None
        best_threshold = None

        for doc_candidate in doc_candidates:
            for live_candidate in live_candidates:
                try:
                    matched, distance, threshold = _verify_pair(doc_candidate, live_candidate)
                except Exception as exc:
                    print(f'[FACE_MATCH] Candidate failed: {ascii(str(exc))}')
                    continue

                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_threshold = threshold

                if matched:
                    print(f'[FACE_MATCH] PASS distance={distance:.4f} threshold={threshold:.4f}')
                    return True

        print(f'[FACE_MATCH] FAIL best_distance={best_distance} threshold={best_threshold}')
        return False
    except Exception as exc:
        print(f'[FACE_MATCH] Error: {ascii(str(exc))}')
        return False
    finally:
        for path in temp_paths:
            try:
                Path(path).unlink()
            except OSError:
                pass
