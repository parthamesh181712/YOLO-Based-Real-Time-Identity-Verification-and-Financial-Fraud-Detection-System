import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib

print("Loading enhanced dataset...")

df = pd.read_csv(r"C:\Users\Acer\Documents\securefin_project\securefin_project\securefin_project\backend\clean_transactions.csv")

# Better feature set
features = df[[
    "amount",
    "old_balance",
    "new_balance",
    "balance_diff",
    "is_night",
    "type"
]]

print("Training improved AML model...")

model = IsolationForest(
    n_estimators=150,
    contamination=0.02,
    random_state=42
)

model.fit(features)

joblib.dump(model, "aml_model.pkl")

print("Improved model saved")