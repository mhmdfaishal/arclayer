from arclayer.domain.enums import IncidentStatus as S
from arclayer.domain.errors import IllegalTransition

_ALLOWED: dict[S, frozenset[S]] = {
    S.RECEIVED: frozenset({S.SAFE_STOPPED, S.ESCALATED, S.AWAITING_RESULT}),
    S.AWAITING_RESULT: frozenset({S.RECOVERED, S.FAILED, S.ESCALATED, S.CENSORED}),
}


def ensure_transition(src: S, dst: S) -> None:
    if dst not in _ALLOWED.get(src, frozenset()):
        raise IllegalTransition(f"{src.value} -> {dst.value} tidak diizinkan")
