"""Unit tests for cohort assignment and onboarding blend weights."""
from ml.cohorts.assign import AccountMeta, assign_cohort
from ml.cohorts.onboarding import check_nrb_rules, compute_blend_weights


def _acct(account_type: str, district: str = "Kathmandu", age: int = 365) -> AccountMeta:
    return AccountMeta(account_id="TEST", account_type=account_type,
                       home_district=district, account_age_days=age)


class TestCohortAssignment:
    def test_overseas_worker(self):
        assert assign_cohort(_acct("REMITTANCE")) == "overseas_worker_remittance"

    def test_salary_kathmandu(self):
        assert assign_cohort(_acct("SALARY", "Kathmandu")) == "salary_kathmandu"

    def test_salary_other(self):
        assert assign_cohort(_acct("SALARY", "Dharan")) == "salary_other"

    def test_savings_urban(self):
        assert assign_cohort(_acct("SAVINGS", "Pokhara")) == "savings_urban"

    def test_savings_rural(self):
        assert assign_cohort(_acct("SAVINGS", "Dhangadhi")) == "savings_rural"

    def test_current_business(self):
        assert assign_cohort(_acct("CURRENT")) == "current_business"

    def test_sita_720_days(self):
        # Sita: SAVINGS, Kathmandu, 720 days → savings_urban
        assert assign_cohort(_acct("SAVINGS", "Kathmandu", 720)) == "savings_urban"


class TestOnboardingBlend:
    def test_day_2_rules_only(self):
        w = compute_blend_weights(2)
        assert w["rules_only"] is True
        assert w["mode"] == "strict_rules"

    def test_day_10_cohort(self):
        w = compute_blend_weights(10)
        assert w["cohort_weight"] == 1.0
        assert w["rules_only"] is False

    def test_day_20_hybrid(self):
        w = compute_blend_weights(20)
        assert w["mode"] == "hybrid"
        assert 0 < w["personal_weight"] < 1

    def test_day_31_personal(self):
        w = compute_blend_weights(31)
        assert w["mode"] == "personal"

    def test_nrb_cap_blocks_large_day1(self):
        passes, reason = check_nrb_rules(80000, age_days=1)
        assert passes is False
        assert reason is not None

    def test_nrb_cap_allows_small_day1(self):
        passes, _ = check_nrb_rules(10000, age_days=1)
        assert passes is True

    def test_nrb_cap_not_applied_after_day3(self):
        passes, _ = check_nrb_rules(200000, age_days=4)
        assert passes is True


# ---------------------------------------------------------------------------
# Storage tests (Redis mock — no live DB required)
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock, patch

from ml.cohorts.storage import cache_cohort, get_cached_cohort, register_account, resolve_cohort


def _fake_redis():
    store: dict = {}
    r = MagicMock()
    r.get.side_effect = lambda k: store.get(k)
    r.set.side_effect = lambda k, v: store.update({k: v})
    r.setex.side_effect = lambda k, ttl, v: store.update({k: v})
    return r, store


class TestCohortStorage:
    def test_cache_and_retrieve(self):
        r, store = _fake_redis()
        cache_cohort("ACC_001", "savings_urban", r=r)
        assert get_cached_cohort("ACC_001", r=r) == "savings_urban"

    def test_cache_miss_returns_none(self):
        r, _ = _fake_redis()
        assert get_cached_cohort("UNKNOWN", r=r) is None

    def test_register_account_caches_cohort(self):
        r, store = _fake_redis()
        meta = AccountMeta("ACC_002", "REMITTANCE", "Kathmandu", 10)
        cohort = register_account(meta, r=r, persist_db=False)
        assert cohort == "overseas_worker_remittance"
        assert get_cached_cohort("ACC_002", r=r) == "overseas_worker_remittance"

    def test_resolve_cohort_from_cache(self):
        r, _ = _fake_redis()
        cache_cohort("ACC_003", "salary_kathmandu", r=r)
        assert resolve_cohort("ACC_003", r=r) == "salary_kathmandu"

    def test_resolve_cohort_fallback_to_meta(self):
        r, _ = _fake_redis()
        meta = AccountMeta("ACC_NEW", "SAVINGS", "Pokhara", 5)
        result = resolve_cohort("ACC_NEW", meta=meta, r=r)
        assert result == "savings_urban"

    def test_resolve_cohort_ultimate_fallback(self):
        r, _ = _fake_redis()
        result = resolve_cohort("TOTALLY_UNKNOWN", r=r)
        assert result == "fallback"
