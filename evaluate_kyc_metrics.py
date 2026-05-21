import json
import os
import sqlite3
from collections import Counter

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), 'database', 'securefin.db')
RESEARCH_DIR = os.path.join(BASE_DIR, '..', 'research_graphs')
os.makedirs(RESEARCH_DIR, exist_ok=True)

STATUS_PNG = os.path.join(RESEARCH_DIR, 'kyc_status_distribution.png')
VALIDATION_PNG = os.path.join(RESEARCH_DIR, 'kyc_validation_parameters.png')
REASON_PNG = os.path.join(RESEARCH_DIR, 'kyc_reason_code_frequency.png')
CONFIDENCE_PNG = os.path.join(RESEARCH_DIR, 'kyc_confidence_timeline.png')
METRICS_JSON = os.path.join(RESEARCH_DIR, 'kyc_metrics.json')

POSITIVE_CODES = {
    'DOB_MATCH': 'DOB Match',
    'NAME_MATCH': 'Name Match',
    'FACE_MATCH_PASS': 'Face Match',
    'SINGLE_PERSON_PASS': 'Single Person',
    'TURN_LEFT_PASS': 'Turn Left',
    'TURN_RIGHT_PASS': 'Turn Right',
    'BLINK_PASS': 'Blink',
}

NEGATIVE_CODES = {
    'NAME_MISMATCH',
    'FACE_MISMATCH',
    'MULTIPLE_PERSONS_DETECTED',
    'TURN_LEFT_FAIL',
    'TURN_RIGHT_FAIL',
    'BLINK_FAIL',
    'FACE_NOT_FOUND_FOR_LIVENESS',
    'LIVENESS_IMAGE_ERROR',
}


def load_kyc_frame():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        'SELECT request_id, customer_id, status, reason_codes, confidence, model_version, created_at FROM kyc_requests ORDER BY created_at',
        conn,
    )
    conn.close()
    if df.empty:
        raise RuntimeError('No KYC records found in database.')
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['reason_codes'] = df['reason_codes'].apply(json.loads)
    return df


def component_pass_rates(df):
    rows = []
    for code, label in POSITIVE_CODES.items():
        applicable = df['reason_codes'].apply(lambda codes: code in codes or any(c.startswith(code.replace('_PASS', '_FAIL')) for c in codes)).sum()
        if code == 'FACE_MATCH_PASS':
            applicable = len(df)
        elif code == 'SINGLE_PERSON_PASS':
            applicable = len(df)
        elif code == 'DOB_MATCH':
            applicable = len(df)
        elif code == 'NAME_MATCH':
            applicable = len(df)
        passed = df['reason_codes'].apply(lambda codes: code in codes).sum()
        pass_rate = (passed / applicable * 100.0) if applicable else None
        rows.append({'label': label, 'applicable': int(applicable), 'passed': int(passed), 'pass_rate': pass_rate})
    return pd.DataFrame(rows)


def main():
    df = load_kyc_frame()

    status_counts = df['status'].value_counts().sort_index()
    reason_counter = Counter()
    for codes in df['reason_codes']:
        reason_counter.update(codes)

    comp_df = component_pass_rates(df)

    verified_rate = float((df['status'] == 'VERIFIED').mean() * 100.0)
    avg_confidence = float(df['confidence'].mean())
    face_match_rate = float(comp_df.loc[comp_df['label'] == 'Face Match', 'pass_rate'].iloc[0] or 0.0)
    blink_pass_rate = float(comp_df.loc[comp_df['label'] == 'Blink', 'pass_rate'].iloc[0] or 0.0)

    metrics = {
        'sample_size': int(len(df)),
        'unique_customers': int(df['customer_id'].nunique()),
        'verified_count': int((df['status'] == 'VERIFIED').sum()),
        'failed_count': int((df['status'] == 'FAILED').sum()),
        'verified_rate_percent': verified_rate,
        'average_confidence': avg_confidence,
        'face_match_pass_rate_percent': face_match_rate,
        'blink_pass_rate_percent': blink_pass_rate,
        'top_reason_codes': reason_counter.most_common(10),
        'note': 'This is operational validation data from stored KYC runs, not ground-truth model accuracy.',
    }

    with open(METRICS_JSON, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)

    plt.figure(figsize=(6, 4))
    plt.bar(status_counts.index, status_counts.values, color=['#d62728' if s == 'FAILED' else '#2ca02c' for s in status_counts.index])
    plt.title('KYC Status Distribution')
    plt.ylabel('Requests')
    plt.tight_layout()
    plt.savefig(STATUS_PNG, dpi=180, bbox_inches='tight')
    plt.close()

    plot_df = comp_df[comp_df['pass_rate'].notna()].copy()
    plt.figure(figsize=(9, 5))
    plt.bar(plot_df['label'], plot_df['pass_rate'], color='#1f77b4')
    plt.ylim(0, 100)
    plt.ylabel('Pass Rate (%)')
    plt.title('KYC Validation Parameter Pass Rates')
    plt.xticks(rotation=25, ha='right')
    plt.tight_layout()
    plt.savefig(VALIDATION_PNG, dpi=180, bbox_inches='tight')
    plt.close()

    top_reasons = reason_counter.most_common(12)
    reason_labels = [item[0] for item in top_reasons]
    reason_values = [item[1] for item in top_reasons]
    plt.figure(figsize=(10, 4))
    plt.plot(df['created_at'], df['confidence'], marker='o', linewidth=2, color='#9467bd')
    plt.title('KYC Confidence Over Time')
    plt.ylabel('Confidence')
    plt.xlabel('Created At')
    plt.xticks(rotation=25, ha='right')
    plt.tight_layout()
    plt.savefig(CONFIDENCE_PNG, dpi=180, bbox_inches='tight')
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(df['created_at'], df['confidence'], marker='o', linewidth=2, color='#9467bd')
    plt.title('KYC Confidence Over Time')
    plt.ylabel('Confidence')
    plt.xlabel('Created At')
    plt.xticks(rotation=25, ha='right')
    plt.tight_layout()
    plt.savefig(CONFIDENCE_PNG, dpi=180, bbox_inches='tight')
    plt.close()

    print('Saved:')
    print(f'  {STATUS_PNG}')
    print(f'  {VALIDATION_PNG}')
    print(f'  {REASON_PNG}')
    print(f'  {CONFIDENCE_PNG}')
    print(f'  {METRICS_JSON}')
    print('\nSummary metrics:')
    for key, value in metrics.items():
        print(f'  {key}: {value}')
    print('\nComponent pass rates:')
    print(comp_df.to_string(index=False))


if __name__ == '__main__':
    main()
