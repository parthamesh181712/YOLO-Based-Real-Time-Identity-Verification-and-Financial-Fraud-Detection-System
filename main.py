import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import sqlite3

from aml import check_aml
from db import fetch_customer_timeline, fetch_user, init_db, insert_aml_decision, insert_audit_log, insert_kyc_request, get_db
from kyc import verify_kyc
from security import create_jwt, decode_jwt, decrypt_bytes, encrypt_bytes, verify_password

app = FastAPI(title='SecureFin Compliance API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'uploads' / 'encrypted'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
init_db()


class LoginRequest(BaseModel):
    username: str
    password: str


class AMLRequest(BaseModel):
    customer_id: str
    amount: float
    old_balance: float
    new_balance: float
    transaction_date: str
    transaction_type: int = 0


DOCUMENT_REGISTRY: Dict[str, Dict[str, str]] = {}


def get_trace_id(request: Request) -> str:
    return request.headers.get('x-trace-id') or str(uuid4())


async def get_current_user(request: Request, authorization: str = Header(default='')) -> Dict[str, str]:
    if not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing or invalid Authorization header')

    token = authorization.split(' ', 1)[1].strip()
    try:
        payload = decode_jwt(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    return {'user_id': str(payload['sub']), 'role': str(payload['role'])}


@app.get('/')
def home():
    return {
        'message': 'SecureFin Compliance API Running',
        'features': ['JWT authentication', 'KYC audit trail', 'Encrypted document storage', 'AML audit trail', 'Guided liveness challenge'],
    }


@app.post('/auth/login')
def login(payload: LoginRequest, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = fetch_user(db, payload.username)
    trace_id = get_trace_id(request)
    ip_address = request.client.host if request.client else 'unknown'

    if not user or not verify_password(payload.password, user['password']):
        insert_audit_log(db, {
            'event_type': 'AUTHENTICATION',
            'actor': payload.username,
            'action': 'LOGIN',
            'target_id': payload.username,
            'result': 'FAILED',
            'ip_address': ip_address,
            'trace_id': trace_id,
            'details': {'reason': 'invalid_credentials'},
            'timestamp': datetime.utcnow().isoformat(),
        })
        raise HTTPException(status_code=401, detail='Invalid username or password')

    token, expiry = create_jwt(user['user_id'], user['role'])
    insert_audit_log(db, {
        'event_type': 'AUTHENTICATION',
        'actor': user['username'],
        'action': 'LOGIN',
        'target_id': user['user_id'],
        'result': 'SUCCESS',
        'ip_address': ip_address,
        'trace_id': trace_id,
        'details': {'role': user['role']},
        'timestamp': datetime.utcnow().isoformat(),
    })

    return {
        'access_token': token,
        'token_type': 'bearer',
        'expires_at': expiry,
        'user': {'user_id': user['user_id'], 'username': user['username'], 'role': user['role']},
    }


@app.post('/kyc/verify')
async def kyc_api(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user),
    customer_id: str = Form(...),
    name: str = Form(...),
    dob: str = Form(...),
    doc_type: str = Form(...),
    liveness_actions: str = Form('TURN_LEFT,BLINK'),
    document: UploadFile = File(...),
    live: UploadFile = File(...),
    live2: UploadFile = File(...),
    live3: UploadFile = File(...),
):
    trace_id = get_trace_id(request)
    ip_address = request.client.host if request.client else 'unknown'
    now = datetime.utcnow()
    request_id = f"KYC_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6].upper()}"

    challenge_sequence = [item.strip().upper() for item in liveness_actions.split(',') if item.strip()]

    doc_bytes = await document.read()
    live_bytes = await live.read()
    live2_bytes = await live2.read()
    live3_bytes = await live3.read()

    temp_paths = []
    try:
        for payload in (doc_bytes, live_bytes, live2_bytes, live3_bytes):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            tmp.write(payload)
            tmp.close()
            temp_paths.append(tmp.name)

        kyc_result = verify_kyc(name, dob, doc_type, temp_paths[0], temp_paths[1], temp_paths[2], temp_paths[3], challenge_sequence)
        encrypted_doc_path = str(UPLOAD_DIR / f'{request_id}_document.enc')
        encrypted_live_path = str(UPLOAD_DIR / f'{request_id}_live.enc')
        encrypted_live2_path = str(UPLOAD_DIR / f'{request_id}_live2.enc')
        encrypted_live3_path = str(UPLOAD_DIR / f'{request_id}_live3.enc')
        Path(encrypted_doc_path).write_bytes(encrypt_bytes(doc_bytes))
        Path(encrypted_live_path).write_bytes(encrypt_bytes(live_bytes))
        Path(encrypted_live2_path).write_bytes(encrypt_bytes(live2_bytes))
        Path(encrypted_live3_path).write_bytes(encrypt_bytes(live3_bytes))

        DOCUMENT_REGISTRY[request_id] = {
            'document': encrypted_doc_path,
            'live': encrypted_live_path,
            'live2': encrypted_live2_path,
            'live3': encrypted_live3_path,
        }

        insert_kyc_request(db, {
            'request_id': request_id,
            'customer_id': customer_id,
            'submitted_by': current_user['user_id'],
            'status': kyc_result['status'],
            'reason_codes': kyc_result['reason_codes'],
            'confidence': kyc_result['confidence'],
            'model_version': kyc_result['model_version'],
            'encrypted_document_path': encrypted_doc_path,
            'encrypted_live_path': encrypted_live_path,
            'encrypted_live2_path': encrypted_live2_path,
            'created_at': now.isoformat(),
        })

        insert_audit_log(db, {
            'event_type': 'KYC_VERIFICATION',
            'actor': current_user['user_id'],
            'action': 'VERIFY_KYC',
            'target_id': customer_id,
            'result': 'SUCCESS' if kyc_result['status'] == 'VERIFIED' else 'FAILED',
            'ip_address': ip_address,
            'trace_id': trace_id,
            'details': {
                'request_id': request_id,
                'reason_codes': kyc_result['reason_codes'],
                'confidence': kyc_result['confidence'],
                'model_version': kyc_result['model_version'],
                'liveness_actions': challenge_sequence,
                'liveness_details': kyc_result.get('liveness_details', {}),
            },
            'timestamp': now.isoformat(),
        })

        return {
            'request_id': request_id,
            'customer_id': customer_id,
            'submitted_by': current_user['user_id'],
            'kyc_status': kyc_result['status'],
            'reason_codes': kyc_result['reason_codes'],
            'confidence': kyc_result['confidence'],
            'model_version': kyc_result['model_version'],
            'liveness_actions': challenge_sequence,
            'liveness_details': kyc_result.get('liveness_details', {}),
            'trace_id': trace_id,
        }
    finally:
        for temp_path in temp_paths:
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.post('/aml/check')
def aml_api(payload: AMLRequest, request: Request, current_user: Dict[str, str] = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    trace_id = get_trace_id(request)
    ip_address = request.client.host if request.client else 'unknown'
    now = datetime.utcnow()
    decision_id = f"AML_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6].upper()}"

    aml_result = check_aml(payload.amount, payload.old_balance, payload.new_balance, payload.transaction_date, payload.transaction_type)

    insert_aml_decision(db, {
        'decision_id': decision_id,
        'customer_id': payload.customer_id,
        'amount': payload.amount,
        'status': aml_result['status'],
        'risk_score': aml_result['risk_score'],
        'reason_codes': aml_result['reason_codes'],
        'model_version': aml_result['model_version'],
        'rule_engine_version': aml_result['rule_engine_version'],
        'created_at': now.isoformat(),
    })

    insert_audit_log(db, {
        'event_type': 'AML_DECISION',
        'actor': current_user['user_id'],
        'action': 'CHECK_AML',
        'target_id': decision_id,
        'result': aml_result['status'],
        'ip_address': ip_address,
        'trace_id': trace_id,
        'details': {
            'customer_id': payload.customer_id,
            'risk_score': aml_result['risk_score'],
            'reason_codes': aml_result['reason_codes'],
            'model_version': aml_result['model_version'],
            'rule_engine_version': aml_result['rule_engine_version'],
            'transaction_type': aml_result['transaction_type'],
        },
        'timestamp': now.isoformat(),
    })

    return {
        'decision_id': decision_id,
        'customer_id': payload.customer_id,
        'amount': payload.amount,
        'status': aml_result['status'],
        'risk_score': aml_result['risk_score'],
        'reason_codes': aml_result['reason_codes'],
        'model_version': aml_result['model_version'],
        'rule_engine_version': aml_result['rule_engine_version'],
        'transaction_type': aml_result['transaction_type'],
        'trace_id': trace_id,
    }


@app.get('/customers/{customer_id}/timeline')
def customer_timeline(customer_id: str, request: Request, current_user: Dict[str, str] = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    trace_id = get_trace_id(request)
    ip_address = request.client.host if request.client else 'unknown'
    timeline = fetch_customer_timeline(db, customer_id)
    insert_audit_log(db, {
        'event_type': 'CUSTOMER_TIMELINE',
        'actor': current_user['user_id'],
        'action': 'VIEW_TIMELINE',
        'target_id': customer_id,
        'result': 'SUCCESS',
        'ip_address': ip_address,
        'trace_id': trace_id,
        'details': {'viewed_sections': ['kyc_requests', 'aml_decisions', 'audit_logs']},
        'timestamp': datetime.utcnow().isoformat(),
    })
    return {'customer_id': customer_id, 'timeline': timeline, 'trace_id': trace_id}


@app.get('/documents/{request_id}/{kind}')
def get_document(request_id: str, kind: str, request: Request, current_user: Dict[str, str] = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    if kind not in {'document', 'live', 'live2', 'live3'}:
        raise HTTPException(status_code=404, detail='Unknown document kind')
    if request_id not in DOCUMENT_REGISTRY or kind not in DOCUMENT_REGISTRY[request_id]:
        raise HTTPException(status_code=404, detail='Encrypted document not found')

    encrypted_path = DOCUMENT_REGISTRY[request_id][kind]
    plaintext = decrypt_bytes(Path(encrypted_path).read_bytes())
    trace_id = get_trace_id(request)
    ip_address = request.client.host if request.client else 'unknown'
    insert_audit_log(db, {
        'event_type': 'DOCUMENT_ACCESS',
        'actor': current_user['user_id'],
        'action': 'VIEW_DOCUMENT',
        'target_id': request_id,
        'result': 'SUCCESS',
        'ip_address': ip_address,
        'trace_id': trace_id,
        'details': {'kind': kind, 'encrypted_path': encrypted_path},
        'timestamp': datetime.utcnow().isoformat(),
    })
    return Response(content=plaintext, media_type='image/jpeg')
