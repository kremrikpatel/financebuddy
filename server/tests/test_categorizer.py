from app.services.categorizer import normalize_merchant, rule_match


def test_normalize_strips_refs():
    raw = "WOOLWORTHS 2211 SYDNEY NSW REF#883746 POS 12/05"
    norm = normalize_merchant(raw)
    assert "#" not in norm
    assert "ref" not in norm.lower()
    assert "woolworths" in norm


def test_normalize_strips_legal_suffix():
    assert normalize_merchant("ACME Pty Ltd") == "acme"


def test_rule_groceries():
    hit = rule_match(normalize_merchant("COSTCO WHOLESALE #123"))
    assert hit and hit[0] == "Groceries"


def test_rule_subscriptions():
    hit = rule_match(normalize_merchant("NETFLIX.COM BILLING"))
    assert hit and hit[0] == "Subscriptions"


def test_rule_salary():
    hit = rule_match(normalize_merchant("PAYROLL DIRECT DEP ACME"))
    assert hit and hit[0] == "Salary"


def test_no_false_rule():
    assert rule_match(normalize_merchant("ZXYQ UNKNOWN SHOP")) is None


def test_looks_multi_item():
    from app.services.categorizer import looks_multi_item

    assert looks_multi_item("Item A and Item B", "Store") is True
    assert looks_multi_item("Coffee $4.50, Muffin $3.50", "Cafe") is True
    assert looks_multi_item(None, "Single Coffee") is False


def test_vector_norm_and_dot():
    from app.services.categorizer import _dot, _norm

    v1 = [3.0, 4.0]
    v2 = [1.0, 2.0]
    assert _norm(v1) == 5.0
    assert _dot(v1, v2) == 11.0
