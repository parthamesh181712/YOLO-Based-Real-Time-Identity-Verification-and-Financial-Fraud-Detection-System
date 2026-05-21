import pandas as pd

print("Loading dataset...")

df = pd.read_csv(r"C:\Users\Acer\Documents\securefin_project\securefin_project\securefin_project\backend\PS_20174392719_1491204439457_log.csv")

print("Dataset loaded")

# Select columns
df = df[[
    "step",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "type"
]]

# Rename
df = df.rename(columns={
    "step": "time_step",
    "oldbalanceOrg": "old_balance",
    "newbalanceOrig": "new_balance"
})

# Feature Engineering

# Balance difference
df["balance_diff"] = df["old_balance"] - df["new_balance"]

# Night transactions (0-6 hours approx)
df["hour"] = df["time_step"] % 24
df["is_night"] = df["hour"].apply(lambda x: 1 if x < 6 else 0)

# Encode transaction type
df["type"] = df["type"].astype("category").cat.codes

df = df.dropna()

df.to_csv("clean_transactions.csv", index=False)

print("Enhanced dataset saved")