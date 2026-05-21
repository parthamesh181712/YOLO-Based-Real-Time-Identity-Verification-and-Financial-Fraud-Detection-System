from ocr import extract_text
from face_match import match_faces
from liveness import check_liveness
from yolo_detector import detect_faces_and_persons

KYC_MODEL_VERSION = 'kyc_face_v2.3'


def verify_kyc(name, dob, doc_type, doc_path, live_path, live2_path, live3_path=None, challenge_sequence=None):
    reason_codes = []
    text = extract_text(doc_path).lower()

    dob_parts = dob.split('-')
    dob_alt = f"{dob_parts[2]}/{dob_parts[1]}/{dob_parts[0]}" if len(dob_parts) == 3 else dob

    if dob_alt in text or dob in text:
        reason_codes.append('DOB_MATCH')
    else:
        reason_codes.append('DOB_MISMATCH')

    persons, _ = detect_faces_and_persons(live_path)
    if persons == 1:
        reason_codes.append('SINGLE_PERSON_PASS')
    else:
        reason_codes.append('MULTIPLE_PERSONS_DETECTED')

    face_match = match_faces(doc_path, live_path)
    if face_match:
        reason_codes.append('FACE_MATCH_PASS')
    else:
        reason_codes.append('FACE_MISMATCH')

    live = check_liveness(live_path, live2_path, live3_path, challenge_sequence)
    reason_codes.extend(live['reason_codes'])

    normalized_name = name.lower().strip()
    name_tokens = [token for token in normalized_name.split() if len(token) > 1]
    if name_tokens and all(token in text for token in name_tokens[:2]):
        reason_codes.append('NAME_MATCH')
    else:
        reason_codes.append('NAME_MISMATCH')

    required_codes = ['DOB_MATCH', 'FACE_MATCH_PASS', 'SINGLE_PERSON_PASS']
    challenge_sequence = challenge_sequence or []
    if 'TURN_LEFT' in challenge_sequence:
        required_codes.append('TURN_LEFT_PASS')
    if 'TURN_RIGHT' in challenge_sequence:
        required_codes.append('TURN_RIGHT_PASS')
    if 'BLINK' in challenge_sequence:
        required_codes.append('BLINK_PASS')

    passed = all(code in reason_codes for code in required_codes)
    confidence = 94.1 if passed else 58.9
    final_status = 'VERIFIED' if passed else 'FAILED'

    print('\n===== KYC CHECK SUMMARY =====')
    print(f'[KYC] Required challenge actions: {challenge_sequence}')
    print(f'[KYC] Reason codes: {reason_codes}')
    print(f"[KYC] Liveness details: {live.get('details', {})}")
    print(f'[KYC] Final status: {final_status}')
    print('===== KYC CHECK SUMMARY END =====\n')

    return {
        'status': final_status,
        'reasons': [code for code in reason_codes if code.endswith('FAIL') or code.endswith('MISMATCH') or code.endswith('DETECTED')],
        'reason_codes': reason_codes,
        'confidence': confidence,
        'model_version': KYC_MODEL_VERSION,
        'liveness_details': live.get('details', {}),
    }
