import pytest
from pydantic import ValidationError

import arclayer.contracts as C
from tests.support.synthetic_host import SyntheticHostAdapter, SyntheticWorld


def _event() -> C.FaultEventIn:
    world = SyntheticWorld(seed=1, n_tasks=3)
    return SyntheticHostAdapter(world).to_fault_event(world.incidents[0], "policy-1")


def test_unknown_fields_are_rejected_so_framework_internals_cannot_leak_in():
    with pytest.raises(ValidationError):
        C.FaultEventIn(**{**_event().model_dump(), "framework_internal_state": {"x": 1}})


def test_only_schema_version_1_0_is_accepted():
    assert _event().schema_version == "1.0"
    with pytest.raises(ValidationError):
        C.FaultEventIn(**{**_event().model_dump(), "schema_version": "2.0"})


def test_messages_are_immutable():
    with pytest.raises(ValidationError):
        _event().task_id = "changed"
