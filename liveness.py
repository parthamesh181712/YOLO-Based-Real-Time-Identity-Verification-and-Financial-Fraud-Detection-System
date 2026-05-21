import cv2
import numpy as np


FRONTAL_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
PROFILE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')


def _load_gray(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None, None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image, gray


def _largest_box(boxes):
    if len(boxes) == 0:
        return None
    return max(boxes, key=lambda b: b[2] * b[3])


def _detect_faces_multimode(gray):
    candidates = []
    frontal_settings = [
        dict(scaleFactor=1.1, minNeighbors=5, minSize=(50, 50)),
        dict(scaleFactor=1.05, minNeighbors=4, minSize=(40, 40)),
        dict(scaleFactor=1.15, minNeighbors=4, minSize=(60, 60)),
    ]

    for params in frontal_settings:
        faces = FRONTAL_CASCADE.detectMultiScale(gray, **params)
        if len(faces) > 0:
            candidates.extend(faces.tolist())

    for flipped in (False, True):
        target = cv2.flip(gray, 1) if flipped else gray
        profiles = PROFILE_CASCADE.detectMultiScale(target, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50))
        for (x, y, w, h) in profiles:
            if flipped:
                x = gray.shape[1] - x - w
            candidates.append([x, y, w, h])

    if not candidates:
        return None, []

    best = _largest_box(candidates)
    center = (best[0] + best[2] / 2, best[1] + best[3] / 2, best[2], best[3])
    return center, candidates


def _detect_blink(base_gray, blink_gray, base_center):
    x_center, y_center, w, h = base_center
    x1 = max(0, int(x_center - w / 2))
    y1 = max(0, int(y_center - h / 2))
    x2 = min(base_gray.shape[1], int(x_center + w / 2))
    y2 = min(base_gray.shape[0], int(y_center + h / 2))

    base_face = base_gray[y1:y2, x1:x2]
    blink_face = blink_gray[y1:y2, x1:x2]
    if base_face.size == 0 or blink_face.size == 0:
        return False

    eye_end = max(1, int(base_face.shape[0] * 0.45))
    diff = cv2.absdiff(base_face[:eye_end, :], blink_face[:eye_end, :])
    _, thresh = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    return int(thresh.sum()) > 9000


def check_liveness(img1_path, img2_path, img3_path=None, challenge_sequence=None):
    _, base_gray = _load_gray(img1_path)
    _, move_gray = _load_gray(img2_path)

    if base_gray is None or move_gray is None:
        return {
            'passed': False,
            'reason_codes': ['LIVENESS_IMAGE_ERROR'],
            'details': {'error': 'Missing liveness image'}
        }

    base_center, base_faces = _detect_faces_multimode(base_gray)
    move_center, move_faces = _detect_faces_multimode(move_gray)
    if base_center is None or move_center is None:
        return {
            'passed': False,
            'reason_codes': ['FACE_NOT_FOUND_FOR_LIVENESS'],
            'details': {'base_faces': len(base_faces), 'move_faces': len(move_faces)}
        }

    challenge_sequence = challenge_sequence or []
    reason_codes = []
    details = {
        'base_faces': len(base_faces),
        'move_faces': len(move_faces),
    }

    horizontal_shift = move_center[0] - base_center[0]
    details['horizontal_shift'] = round(float(horizontal_shift), 2)

    if 'TURN_LEFT' in challenge_sequence:
        if horizontal_shift < -10:
            reason_codes.append('TURN_LEFT_PASS')
        else:
            reason_codes.append('TURN_LEFT_FAIL')

    if 'TURN_RIGHT' in challenge_sequence:
        if horizontal_shift > 10:
            reason_codes.append('TURN_RIGHT_PASS')
        else:
            reason_codes.append('TURN_RIGHT_FAIL')

    if 'BLINK' in challenge_sequence:
        if not img3_path:
            reason_codes.append('BLINK_FAIL')
        else:
            _, blink_gray = _load_gray(img3_path)
            if blink_gray is None:
                reason_codes.append('BLINK_FAIL')
            elif _detect_blink(base_gray, blink_gray, base_center):
                reason_codes.append('BLINK_PASS')
            else:
                reason_codes.append('BLINK_FAIL')

    passed = all(code.endswith('_PASS') for code in reason_codes) and len(reason_codes) > 0
    return {
        'passed': passed,
        'reason_codes': reason_codes,
        'details': details
    }
