"""Behavior Agent — per-cohort LSTM + Isolation Forest ensemble."""
from __future__ import annotations

import json
import math
import os
import pathlib
import pickle
import time
from typing import Any

import numpy as np
import redis
import torch

from ml.cohorts.assign import AccountMeta, assign_cohort
from ml.cohorts.onboarding import check_nrb_rules, compute_blend_weights
from ml.training.featurize import FEATURE_COLS
from ml.training.train_lstm import BehaviorLSTM
from orchestrator.schemas import AgentScore, TransactionEvent

ARTIFACTS_DIR = pathlib.Path("ml/artifacts")
SEQ_LEN = 20
_DEVICE = torch.device("cpu")


class BehaviorAgent:
    AGENT_NAME = "behavior"

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._if_models: dict[str, Any] = {}
        self._lstm_models: dict[str, BehaviorLSTM] = {}
        self._registry_enabled = os.environ.get("MLFLOW_MODEL_REGISTRY_ENABLED", "false").lower() == "true"
        self._mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5050")
        self._load_models()

    def _load_models(self) -> None:
        if self._registry_enabled:
            try:
                self._load_from_registry()
                if self._if_models:  # success
                    return
            except Exception as e:
                print(f"MLflow registry load failed, falling back to disk: {e}")

        # Fallback to local files
        for path in ARTIFACTS_DIR.glob("if_*.pkl"):
            cohort = path.stem[3:]  # strip "if_"
            with open(path, "rb") as f:
                self._if_models[cohort] = pickle.load(f)

        for path in ARTIFACTS_DIR.glob("lstm_*.pt"):
            cohort = path.stem[5:]  # strip "lstm_"
            model = BehaviorLSTM(input_dim=len(FEATURE_COLS))
            state = torch.load(path, map_location=_DEVICE, weights_only=True)
            model.load_state_dict(state)
            model.eval()
            self._lstm_models[cohort] = model

    def _load_from_registry(self) -> None:
        import mlflow
        mlflow.set_tracking_uri(self._mlflow_uri)
        client = mlflow.tracking.MlflowClient()
        
        cohorts = ["current_business", "overseas_worker_remittance", "salary_kathmandu", "salary_other", "savings_rural", "savings_urban"]
        for cohort in cohorts:
            try:
                # Load IF
                if_name = f"if_{cohort}"
                if_mv = client.get_latest_versions(if_name, stages=["Production"])
                if if_mv:
                    local_path = mlflow.artifacts.download_artifacts(artifact_uri=if_mv[0].source)
                    with open(local_path, "rb") as f:
                        self._if_models[cohort] = pickle.load(f)
                
                # Load LSTM
                lstm_name = f"lstm_{cohort}"
                lstm_mv = client.get_latest_versions(lstm_name, stages=["Production"])
                if lstm_mv:
                    local_path = mlflow.artifacts.download_artifacts(artifact_uri=lstm_mv[0].source)
                    model = BehaviorLSTM(input_dim=len(FEATURE_COLS))
                    state = torch.load(local_path, map_location=_DEVICE, weights_only=True)
                    model.load_state_dict(state)
                    model.eval()
                    self._lstm_models[cohort] = model
            except Exception as e:
                print(f"Failed to load {cohort} from registry: {e}")

    def score(self, tx: TransactionEvent, account_meta: AccountMeta | None = None) -> AgentScore:
        t0 = time.perf_counter()

        # Resolve cohort
        if account_meta is None:
            account_meta = AccountMeta(
                account_id=tx.account_id,
                account_type=tx.account_type,
                home_district=tx.account_home_district,
                account_age_days=tx.account_age_days,
            )
        cohort = assign_cohort(account_meta)
        blend = compute_blend_weights(tx.account_age_days)

        reason_codes: list[str] = []

        # Strict rules mode (days 0-3) — abstain from ML
        if blend["rules_only"]:
            passes, reason = check_nrb_rules(tx.amount_npr, tx.account_age_days)
            score = 0.0 if passes else 0.85
            if reason:
                reason_codes.append(reason)
            reason_codes.append("mode:strict_rules")
            return AgentScore(
                agent="behavior", score=round(score, 4),
                reason_codes=reason_codes,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        features = self._extract_features(tx)
        seq = self._load_sequence(tx.account_id, features)
        n_history = self._sequence_length(tx.account_id)

        if_score = self._run_if(cohort, features, reason_codes)

        # Cold-start: < 5 tx → IF only
        if n_history < 5 or cohort not in self._lstm_models:
            reason_codes.append("mode:if_only")
            final = if_score
        else:
            lstm_score = self._run_lstm(cohort, seq, reason_codes)
            final = 0.6 * lstm_score + 0.4 * if_score
            reason_codes.append(f"mode:ensemble_cohort={cohort}")

        self._update_sequence(tx.account_id, features)

        return AgentScore(
            agent="behavior",
            score=round(min(1.0, max(0.0, final)), 4),
            reason_codes=reason_codes,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    # ------------------------------------------------------------------
    def _extract_features(self, tx: TransactionEvent) -> np.ndarray:
        import math as _math
        hour = tx.timestamp.hour
        dow = tx.timestamp.weekday()
        tx_type_vec = [float(tx.transaction_type == t) for t in ["P2P", "QR_ESEWA", "SWIFT_REMITTANCE", "ATM_POS"]]
        vec = [
            math.log1p(tx.amount_npr),
            math.sin(2 * _math.pi * hour / 24),
            math.cos(2 * _math.pi * hour / 24),
            math.sin(2 * _math.pi * dow / 7),
            math.cos(2 * _math.pi * dow / 7),
            float(dow >= 5),
            0.0,   # amount_zscore — unknown at inference without history
            0.0,   # inter_tx_s — filled from sequence
            0.0,   # merchant_seen — filled from sequence
        ] + tx_type_vec
        return np.array(vec, dtype=np.float32)

    def _load_sequence(self, account_id: str, current: np.ndarray) -> np.ndarray:
        raw = self._r.get(f"behavior:seq:{account_id}")
        if raw:
            hist = np.array(json.loads(raw), dtype=np.float32)
        else:
            hist = np.zeros((0, len(FEATURE_COLS)), dtype=np.float32)
        seq = np.vstack([hist, current[np.newaxis, :]]) if len(hist) else current[np.newaxis, :]
        seq = seq[-SEQ_LEN:]
        if len(seq) < SEQ_LEN:
            pad = np.zeros((SEQ_LEN - len(seq), len(FEATURE_COLS)), dtype=np.float32)
            seq = np.vstack([pad, seq])
        return seq

    def _sequence_length(self, account_id: str) -> int:
        raw = self._r.get(f"behavior:seq:{account_id}")
        if not raw:
            return 0
        return len(json.loads(raw))

    def _update_sequence(self, account_id: str, features: np.ndarray) -> None:
        raw = self._r.get(f"behavior:seq:{account_id}")
        hist = json.loads(raw) if raw else []
        hist.append(features.tolist())
        hist = hist[-SEQ_LEN:]
        self._r.set(f"behavior:seq:{account_id}", json.dumps(hist))

    def _run_if(self, cohort: str, features: np.ndarray, reason_codes: list[str]) -> float:
        model = self._if_models.get(cohort) or self._if_models.get("fallback")
        if model is None:
            reason_codes.append("if_model_unavailable")
            return 0.5
        raw = model.decision_function(features.reshape(1, -1))[0]
        # Normalise: decision_function returns negative for anomalies
        score = float(1 / (1 + math.exp(raw * 5)))  # sigmoid inversion
        return score

    def _run_lstm(self, cohort: str, seq: np.ndarray, reason_codes: list[str]) -> float:
        model = self._lstm_models.get(cohort) or self._lstm_models.get("fallback")
        if model is None:
            reason_codes.append("lstm_model_unavailable")
            return 0.5
        x = torch.tensor(seq[np.newaxis, :, :], dtype=torch.float32)
        with torch.no_grad():
            return float(model(x).item())
