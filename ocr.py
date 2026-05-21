import os
import re

import cv2
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"


def _score_ocr_text(text: str) -> int:
    score = 0
    lowered = text.lower()

    keyword_weights = {
        'government': 8,
        'india': 8,
        'dob': 12,
        'male': 8,
        'female': 8,
        'aadhaar': 10,
        'suraj': 20,
        'prakash': 20,
        'konda': 20,
        '6251': 15,
        '5079': 15,
        '8336': 15,
    }

    for keyword, weight in keyword_weights.items():
        if keyword in lowered:
            score += weight

    if re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text):
        score += 40
    if re.search(r'\b\d{2}/\d{2}/\d{4}\b', text):
        score += 25

    score += min(len(text.strip()) // 20, 20)
    return score


def _ocr_variants(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    return {
        'gray_default': (gray, ''),
        'gray_psm6': (gray, '--psm 6'),
        'gray_psm11': (gray, '--psm 11'),
        'thresh_psm6': (cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], '--psm 6'),
        'thresh_psm11': (cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], '--psm 11'),
        'adaptive_psm6': (
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11),
            '--psm 6',
        ),
        'adaptive_psm11': (
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11),
            '--psm 11',
        ),
    }


def extract_text(path):
    img = cv2.imread(path)
    if img is None:
        print(f"[OCR] Could not read image: {path}")
        return ""

    best_name = ''
    best_text = ''
    best_score = -1

    for variant_name, (variant_img, config) in _ocr_variants(img).items():
        text = pytesseract.image_to_string(variant_img, config=config)
        score = _score_ocr_text(text)
        if score > best_score:
            best_score = score
            best_name = variant_name
            best_text = text

    print('\n===== OCR EXTRACTED TEXT START =====')
    print('[OCR] Orientation used: original_only')
    print(f'[OCR] Best pipeline: {best_name}')
    print(best_text)
    print('===== OCR EXTRACTED TEXT END =====\n')

    return best_text.lower()
