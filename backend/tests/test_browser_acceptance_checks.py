import pytest

from tools.acceptance_browser import check_known_answer


@pytest.mark.parametrize("kind,text,citations", [
    ("penalty", "2024年罚款36元。", ["R11"]),
    ("penalty", "2024年罚款36万元。", ["unrelated"]),
    ("penalty", "2024年罚款136万元。", ["R11"]),
    ("penalty", "2024年被处136万元罚款。", ["R11"]),
    ("revenue", "营业收入为38798611元；原表另有千元单位。", ["R20"]),
    ("revenue", "营业收入为38,798,611千元。", ["unrelated"]),
    ("revenue", "2025年营业收入为138798611千元。", ["R20"]),
    ("revenue", "2025年营业收入（千元）：387986110。", ["R20"]),
])
def test_known_answer_rejects_wrong_units_or_unrelated_sources(kind, text, citations):
    with pytest.raises(AssertionError):
        check_known_answer(kind, {"text": text, "citations": citations}, {"R11", "R20"})


@pytest.mark.parametrize("kind,text,ref", [
    ("penalty", "2024年责令改正，给予警告，并处36万元罚款。", "R11"),
    ("penalty", "2024年罚款36万元。", "R11"),
    ("revenue", "2025年营业收入为38,798,611千元。", "R20"),
    ("revenue", "营业收入（人民币千元）：38,798,611。", "R20"),
])
def test_known_answer_accepts_supported_amount_and_unit(kind, text, ref):
    check_known_answer(kind, {"text": text, "citations": [ref]}, {ref})
