"""4-stage cohort onboarding blend weights from concept paper Section 4.3."""
from __future__ import annotations

# NRB-style daily amount cap for days 0-3 (strict rules mode)
NRB_DAILY_CAP_NPR = 50_000.0


def compute_blend_weights(age_days: int) -> dict:
    """
    Returns weights dict with keys: mode, cohort_weight, personal_weight, rules_only.

    Stages:
      0-3   → rules_only (behavior abstains)
      4-14  → cohort 100%
      15-30 → linear blend toward personal
      31+   → personal (hackathon shortcut: stays on cohort model)
    """
    if age_days <= 3:
        return {"mode": "strict_rules", "cohort_weight": 0.0, "personal_weight": 0.0, "rules_only": True}
    if age_days <= 14:
        return {"mode": "cohort", "cohort_weight": 1.0, "personal_weight": 0.0, "rules_only": False}
    if age_days <= 30:
        personal_w = (age_days - 14) / 16.0
        return {"mode": "hybrid", "cohort_weight": 1.0 - personal_w, "personal_weight": personal_w, "rules_only": False}
    # 31+ — hackathon shortcut: stay on cohort
    return {"mode": "personal", "cohort_weight": 0.0, "personal_weight": 1.0, "rules_only": False}


def check_nrb_rules(amount_npr: float, age_days: int) -> tuple[bool, str | None]:
    """Returns (passes, reason). Used during strict_rules mode (days 0-3)."""
    if age_days <= 3 and amount_npr > NRB_DAILY_CAP_NPR:
        return False, f"nrb_new_account_cap:{amount_npr:.0f}>{NRB_DAILY_CAP_NPR:.0f}"
    return True, None
