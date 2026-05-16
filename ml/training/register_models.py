"""Register trained models in MLflow Model Registry and promote to Production."""
from __future__ import annotations

import mlflow
from mlflow.tracking import MlflowClient

MLFLOW_URI = "http://localhost:5050"

COHORTS = [
    "current_business",
    "overseas_worker_remittance",
    "salary_kathmandu",
    "salary_other",
    "savings_rural",
    "savings_urban",
]

def register_models():
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    for cohort in COHORTS:
        # 1. Register Isolation Forest
        exp_if = client.get_experiment_by_name("isolation_forest")
        runs_if = client.search_runs(
            experiment_ids=[exp_if.experiment_id],
            filter_string=f"params.cohort = '{cohort}'",
            order_by=["metrics.auc DESC"],
            max_results=1,
        )
        if runs_if:
            run_id = runs_if[0].info.run_id
            model_name = f"if_{cohort}"
            # Create registered model if not exists
            try:
                client.create_registered_model(model_name)
            except:
                pass
            
            # Create model version
            source = f"{runs_if[0].info.artifact_uri}/if_{cohort}.pkl"
            mv = client.create_model_version(model_name, source, run_id)
            client.transition_model_version_stage(model_name, mv.version, "Production")
            print(f"Registered IF for {cohort} (v{mv.version}) -> Production")

        # 2. Register LSTM
        exp_lstm = client.get_experiment_by_name("behavior_lstm")
        runs_lstm = client.search_runs(
            experiment_ids=[exp_lstm.experiment_id],
            filter_string=f"params.cohort = '{cohort}'",
            order_by=["metrics.auc DESC"],
            max_results=1,
        )
        if runs_lstm:
            run_id = runs_lstm[0].info.run_id
            model_name = f"lstm_{cohort}"
            try:
                client.create_registered_model(model_name)
            except:
                pass
            
            source = f"{runs_lstm[0].info.artifact_uri}/lstm_{cohort}.pt"
            mv = client.create_model_version(model_name, source, run_id)
            client.transition_model_version_stage(model_name, mv.version, "Production")
            print(f"Registered LSTM for {cohort} (v{mv.version}) -> Production")

if __name__ == "__main__":
    register_models()
