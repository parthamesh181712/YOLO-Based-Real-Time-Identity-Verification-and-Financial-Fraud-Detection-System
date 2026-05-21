import json
import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'PS_20174392719_1491204439457_log.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'aml_model.pkl')

RESEARCH_DIR = os.path.join(BASE_DIR, '..', 'research_graphs')
os.makedirs(RESEARCH_DIR, exist_ok=True)

EVAL_PNG = os.path.join(RESEARCH_DIR, 'aml_performance_graph.png')
CM_PNG = os.path.join(RESEARCH_DIR, 'aml_confusion_matrix.png')
METRICS_JSON = os.path.join(RESEARCH_DIR, 'aml_metrics.json')
REPORT_TXT = os.path.join(RESEARCH_DIR, 'aml_classification_report.txt')

MAX_NON_FRAUD = 100000
RANDOM_STATE = 42


def load_evaluation_frame():
    usecols = ['step', 'amount', 'oldbalanceOrg', 'newbalanceOrig', 'type', 'isFraud']
    df = pd.read_csv(DATA_PATH, usecols=usecols)

    fraud_df = df[df['isFraud'] == 1]
    non_fraud_df = df[df['isFraud'] == 0]

    if len(non_fraud_df) > MAX_NON_FRAUD:
        non_fraud_df = non_fraud_df.sample(MAX_NON_FRAUD, random_state=RANDOM_STATE)

    eval_df = pd.concat([fraud_df, non_fraud_df], ignore_index=True)
    eval_df = eval_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True)

    eval_df = eval_df.rename(columns={
        'step': 'time_step',
        'oldbalanceOrg': 'old_balance',
        'newbalanceOrig': 'new_balance',
    })

    eval_df['balance_diff'] = eval_df['old_balance'] - eval_df['new_balance']
    eval_df['hour'] = eval_df['time_step'] % 24
    eval_df['is_night'] = (eval_df['hour'] < 6).astype(int)
    eval_df['type'] = eval_df['type'].astype('category').cat.codes
    eval_df = eval_df.dropna()
    return eval_df


def main():
    print('Loading AML model...')
    model = joblib.load(MODEL_PATH)

    print('Preparing evaluation dataset...')
    df = load_evaluation_frame()

    feature_columns = ['amount', 'old_balance', 'new_balance', 'balance_diff', 'is_night', 'type']
    X = df[feature_columns]
    y_true = df['isFraud'].astype(int).to_numpy()

    print(f'Evaluating on {len(df)} transactions ({int(y_true.sum())} fraud, {int((y_true == 0).sum())} non-fraud)...')

    anomaly_scores = -model.decision_function(X)
    y_pred = (model.predict(X) == -1).astype(int)

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()

    roc_auc = roc_auc_score(y_true, anomaly_scores)
    avg_precision = average_precision_score(y_true, anomaly_scores)
    report = classification_report(y_true, y_pred, digits=4)

    metrics = {
        'sample_size': int(len(df)),
        'fraud_count': int(y_true.sum()),
        'non_fraud_count': int((y_true == 0).sum()),
        'true_negative': int(tn),
        'false_positive': int(fp),
        'false_negative': int(fn),
        'true_positive': int(tp),
        'precision': float(tp / (tp + fp)) if (tp + fp) else 0.0,
        'recall': float(tp / (tp + fn)) if (tp + fn) else 0.0,
        'specificity': float(tn / (tn + fp)) if (tn + fp) else 0.0,
        'accuracy': float((tp + tn) / len(y_true)),
        'f1_score': float((2 * tp) / ((2 * tp) + fp + fn)) if ((2 * tp) + fp + fn) else 0.0,
        'roc_auc': float(roc_auc),
        'average_precision': float(avg_precision),
    }

    with open(METRICS_JSON, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)

    with open(REPORT_TXT, 'w', encoding='utf-8') as f:
        f.write(report)

    fpr, tpr, _ = roc_curve(y_true, anomaly_scores)
    pr_precision, pr_recall, _ = precision_recall_curve(y_true, anomaly_scores)

    plt.figure(figsize=(13, 5))

    plt.subplot(1, 2, 1)
    plt.plot(fpr, tpr, label=f'ROC AUC = {roc_auc:.3f}', color='#1f77b4', linewidth=2)
    plt.plot([0, 1], [0, 1], linestyle='--', color='#888888')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('AML Model ROC Curve')
    plt.legend(loc='lower right')
    plt.grid(alpha=0.25)

    plt.subplot(1, 2, 2)
    plt.plot(pr_recall, pr_precision, label=f'AP = {avg_precision:.3f}', color='#d62728', linewidth=2)
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('AML Model Precision-Recall Curve')
    plt.legend(loc='lower left')
    plt.grid(alpha=0.25)

    plt.tight_layout()
    plt.savefig(EVAL_PNG, dpi=180, bbox_inches='tight')
    plt.close()

    fig, ax = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Non-Fraud', 'Fraud'])
    disp.plot(ax=ax, cmap='Blues', colorbar=False)
    ax.set_title('AML Confusion Matrix')
    plt.tight_layout()
    plt.savefig(CM_PNG, dpi=180, bbox_inches='tight')
    plt.close(fig)

    print('Saved:')
    print(f'  {EVAL_PNG}')
    print(f'  {CM_PNG}')
    print(f'  {METRICS_JSON}')
    print(f'  {REPORT_TXT}')
    print('\nClassification report:\n')
    print(report)
    print('Summary metrics:')
    for key, value in metrics.items():
        print(f'  {key}: {value}')


if __name__ == '__main__':
    main()
