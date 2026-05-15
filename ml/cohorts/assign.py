"""Cohort assignment — first-match rules from concept paper Section 4.3."""
from __future__ import annotations

from dataclasses import dataclass

URBAN_DISTRICTS = {"Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara"}

COHORT_RULES: list[tuple[str, object]] = [
    ("overseas_worker_remittance", lambda a: a.account_type == "REMITTANCE"),
    ("salary_kathmandu",           lambda a: a.account_type == "SALARY" and a.home_district == "Kathmandu"),
    ("salary_other",               lambda a: a.account_type == "SALARY"),
    ("savings_urban",              lambda a: a.account_type == "SAVINGS" and a.home_district in URBAN_DISTRICTS),
    ("savings_rural",              lambda a: a.account_type == "SAVINGS"),
    ("current_business",           lambda a: a.account_type == "CURRENT"),
    ("fallback",                   lambda a: True),
]


@dataclass
class AccountMeta:
    account_id: str
    account_type: str   # SAVINGS | CURRENT | SALARY | REMITTANCE
    home_district: str
    account_age_days: int


def assign_cohort(account: AccountMeta) -> str:
    for cohort_name, predicate in COHORT_RULES:
        if predicate(account):
            return cohort_name
    return "fallback"  # unreachable but satisfies type checker
