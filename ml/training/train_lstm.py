"""Train one BehaviorLSTM per cohort, save checkpoints, log to MLflow."""
from __future__ import annotations

import pathlib

import mlflow
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset

from ml.cohorts.assign import AccountMeta, assign_cohort
from ml.training.featurize import FEATURE_COLS, featurize
from data.loader import load_accounts, load_labels, load_transactions

ARTIFACTS_DIR = pathlib.Path("ml/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

SEQ_LEN = 20
HIDDEN_DIM = 64
EPOCHS = 20
BATCH = 64
LR = 1e-3


class BehaviorLSTM(nn.Module):
    def __init__(self, input_dim: int = len(FEATURE_COLS), hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=2, batch_first=True, dropout=0.2)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(),
            nn.Linear(32, 1), nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(1)


class TxSequenceDataset(Dataset):
    def __init__(self, sequences: np.ndarray, labels: np.ndarray):
        self.X = torch.tensor(sequences, dtype=torch.float32)
        self.y = torch.tensor(labels, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int):
        return self.X[idx], self.y[idx]


def _build_sequences(grp: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Slide a window of SEQ_LEN over each account's sorted transactions."""
    seqs, labs = [], []
    for _, acct_df in grp.groupby("account_id"):
        acct_df = acct_df.sort_values("timestamp")
        X = acct_df[FEATURE_COLS].values.astype(np.float32)
        y = acct_df["is_fraud"].values.astype(np.float32)
        for i in range(len(X)):
            start = max(0, i - SEQ_LEN + 1)
            seq = X[start : i + 1]
            # Pad left if shorter than SEQ_LEN
            if len(seq) < SEQ_LEN:
                pad = np.zeros((SEQ_LEN - len(seq), X.shape[1]), dtype=np.float32)
                seq = np.vstack([pad, seq])
            seqs.append(seq)
            labs.append(y[i])
    return np.array(seqs), np.array(labs)


def train_all(mlflow_uri: str = "http://localhost:5050") -> None:
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("behavior_lstm")

    txs = load_transactions()
    accts = load_accounts()
    labels = load_labels()

    features = featurize(txs, accts)
    features = features.merge(labels[["transaction_id", "is_fraud"]], on="transaction_id", how="left")
    features["is_fraud"] = features["is_fraud"].fillna(False)

    acct_cohort = {}
    for _, row in accts.iterrows():
        meta = AccountMeta(
            account_id=row["account_id"],
            account_type=row["account_type"],
            home_district=row["home_district"],
            account_age_days=int(row["account_age_days"]),
        )
        acct_cohort[row["account_id"]] = assign_cohort(meta)
    features["cohort"] = features["account_id"].map(acct_cohort).fillna("fallback")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    for cohort, grp in features.groupby("cohort"):
        seqs, labs = _build_sequences(grp)
        if len(seqs) < 10:
            print(f"  [{cohort}] skipped — too few samples ({len(seqs)})")
            continue

        split = int(len(seqs) * 0.8)
        train_ds = TxSequenceDataset(seqs[:split], labs[:split])
        val_ds = TxSequenceDataset(seqs[split:], labs[split:])
        train_dl = DataLoader(train_ds, batch_size=BATCH, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=BATCH)

        model = BehaviorLSTM(input_dim=len(FEATURE_COLS)).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=LR)
        criterion = nn.BCELoss()

        best_auc, best_state = 0.0, None
        with mlflow.start_run(run_name=f"LSTM_{cohort}"):
            mlflow.log_params({"cohort": cohort, "epochs": EPOCHS, "seq_len": SEQ_LEN, "hidden": HIDDEN_DIM})

            for epoch in range(EPOCHS):
                model.train()
                for xb, yb in train_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    opt.zero_grad()
                    criterion(model(xb), yb).backward()
                    opt.step()

                # Validation
                model.eval()
                preds, trues = [], []
                with torch.no_grad():
                    for xb, yb in val_dl:
                        preds.extend(model(xb.to(device)).cpu().numpy())
                        trues.extend(yb.numpy())

                auc = roc_auc_score(trues, preds) if sum(trues) > 0 else 0.5
                mlflow.log_metric("val_auc", auc, step=epoch)

                if auc > best_auc:
                    best_auc = auc
                    best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            path = ARTIFACTS_DIR / f"lstm_{cohort}.pt"
            torch.save(best_state, path)
            mlflow.log_metric("best_auc", best_auc)
            mlflow.log_artifact(str(path))
            print(f"  [{cohort}] best_auc={best_auc:.3f}, saved → {path}")

    print("LSTM training complete.")


if __name__ == "__main__":
    train_all()
