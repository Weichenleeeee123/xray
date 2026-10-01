from app.sources.licenses import LicenseIndex

idx = LicenseIndex.load()


def test_count_matches_official_list():
    assert len(idx) == idx.meta["count"] == 4070


def test_exact_name_found():
    hit = idx.lookup("杭州银行股份有限公司")
    assert hit.found
    assert hit.record.type == "城市商业银行"


def test_short_name_gives_full_name_as_suggestion():
    hit = idx.lookup("杭州银行")
    assert not hit.found
    assert "杭州银行股份有限公司" in [s.name for s in hit.suggestions]


def test_branch_points_to_its_legal_entity():
    hit = idx.lookup("杭州银行股份有限公司西湖支行")
    assert not hit.found
    assert hit.suggestions[0].name == "杭州银行股份有限公司"


def test_halfwidth_parentheses_match_fullwidth():
    name = next(n for n in idx._by_name if "（" in n)
    assert idx.lookup(name.replace("（", "(").replace("）", ")")).found


def test_fictional_company_not_found():
    hit = idx.lookup("杭州满盈禾康养健康咨询有限公司")
    assert not hit.found
    assert hit.suggestions == []
