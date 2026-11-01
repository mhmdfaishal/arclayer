import pytest

from arclayer.domain.answer_matching import answers_match
from arclayer.domain.enums import IncidentStatus as S
from arclayer.domain.errors import IllegalTransition
from arclayer.domain.state_machine import ensure_transition

ALLOWED = {
    (S.RECEIVED, S.SAFE_STOPPED),
    (S.RECEIVED, S.ESCALATED),
    (S.RECEIVED, S.AWAITING_RESULT),
    (S.AWAITING_RESULT, S.RECOVERED),
    (S.AWAITING_RESULT, S.FAILED),
    (S.AWAITING_RESULT, S.ESCALATED),
    (S.AWAITING_RESULT, S.CENSORED),
}


@pytest.mark.parametrize("src", list(S))
@pytest.mark.parametrize("dst", list(S))
def test_transition_table(src, dst):
    if (src, dst) in ALLOWED:
        ensure_transition(src, dst)
    else:
        with pytest.raises(IllegalTransition):
            ensure_transition(src, dst)


@pytest.mark.parametrize(
    "pred,truth,ok",
    [
        ("Paris", "paris", True),
        ("  Paris. ", "Paris", True),
        ("$1,000", "1000", True),
        ("12.50", "12.5", True),
        ("3", "4", False),
        ("a, b; c", "a,b,c", True),
        ("a, c, b", "a,b,c", False),
        ("New  York", "new york", True),
        (None, "x", False),
    ],
)
def test_gaia_like_answer_matching(pred, truth, ok):
    assert answers_match(pred, truth) is ok
