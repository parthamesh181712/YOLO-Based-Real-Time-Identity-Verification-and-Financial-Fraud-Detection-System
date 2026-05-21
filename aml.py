from datetime import datetime
import numpy as np
import os
import joblib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(BASE_DIR, 'aml_model.pkl')

AML_MODEL_VERSION = 'aml_iforest_v1.3'
RULE_ENGINE_VERSION = 'rules_v1.1'
model = joblib.load(model_path)


def check_aml(amount, old_balance, new_balance, transaction_date, transaction_type=0):
    hour = datetime.fromisoformat(str(transaction_date).replace('Z', '+00:00')).hour
    is_night = 1 if hour < 6 else 0
    balance_diff = old_balance - new_balance
    transaction_type = int(transaction_type)

    features = np.array([[amount, old_balance, new_balance, balance_diff, is_night, transaction_type]])
    raw_score = float(model.decision_function(features)[0])
    risk_score = min(max((raw_score + 0.5) * 100, 0), 100)

    reason_codes = ['MODEL_ANOMALY_HIGH'] if risk_score >= 65 else ['MODEL_ANOMALY_LOW']
    if amount >= 90000:
        reason_codes.append('AMOUNT_SPIKE')
        risk_score = max(risk_score, 78)
    if is_night:
        reason_codes.append('UNUSUAL_HOUR')
        risk_score = max(risk_score, 72)
    if amount > 200000:
        risk_score = max(risk_score, 95)
        reason_codes.append('RULE_LIMIT_BREACH')

    if risk_score > 80:
        status = 'BLOCK'
    elif risk_score > 40:
        status = 'REVIEW'
    else:
        status = 'ALLOW'

    return {
        'risk_score': round(risk_score, 2),
        'status': status,
        'reason_codes': reason_codes,
        'model_version': AML_MODEL_VERSION,
        'rule_engine_version': RULE_ENGINE_VERSION,
        'raw_anomaly_score': round(raw_score, 5),
        'transaction_type': transaction_type,
    }
