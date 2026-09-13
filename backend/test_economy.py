import economy


def test_result_hash_stable():
    a = economy.result_hash({"b": 1, "a": 2})
    b = economy.result_hash({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64


def test_tx_hash_format():
    h = economy.result_hash({"x": 1})
    tx = economy.tx_hash("task-123", h)
    assert tx.startswith("0x")
    assert len(tx) == 66


def test_owner_address_deterministic():
    assert economy.owner_address("coder") == economy.owner_address("coder")
    assert economy.owner_address("coder").startswith("0x")
    assert len(economy.owner_address("coder")) == 42


def test_compute_scores_bounds_and_badge():
    s = economy.compute_scores(done=40, failed=0, avg_duration_sec=5.0)
    assert 0 <= s["composite"] <= 1000
    assert s["success_rate"] == 1.0
    assert economy.badge_for(850) == "Gold"
    assert economy.badge_for(650) == "Silver"
    assert economy.badge_for(100) == "Bronze"


def test_compute_scores_no_history_is_neutral():
    s = economy.compute_scores(done=0, failed=0, avg_duration_sec=0.0)
    assert 0 <= s["composite"] <= 1000


def test_delta_cap():
    assert economy.apply_delta_cap(500, 1000) == 600   # +20% max
    assert economy.apply_delta_cap(500, 100) == 400    # -20% max
    assert economy.apply_delta_cap(0, 800) == 800      # no cap when prev==0
