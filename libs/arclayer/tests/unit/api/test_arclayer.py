"""ArcLayer: the class a host imports. One host, one ArcLayer, no network."""

import asyncio
import pathlib
from concurrent.futures import ThreadPoolExecutor

import pytest

import arclayer.contracts as C
from arclayer import ArcLayer, Conflict, FeatureMismatch, InvalidRewardWeights, NotFound, PolicyBusy
from tests.support.synthetic_host import SyntheticHostAdapter, SyntheticWorld, synthetic_candidates

CONFIGS = pathlib.Path(__file__).resolve().parents[3] / "configs"


def _setup(db_url=None, n_tasks=30, seed=3):
    world = SyntheticWorld(seed=seed, n_tasks=n_tasks)
    layer = ArcLayer(db_url, candidates=synthetic_candidates())
    for task_id, answer in world.oracle.items():
        layer.register_ground_truth(task_id, answer)
    return layer, world, SyntheticHostAdapter(world)


def _first_execute(layer, adapter, world, policy_id):
    """Post incidents until one gets an execute command; return (command, index)."""
    for i, incident in enumerate(world.incidents):
        command = layer.post_incident(adapter.to_fault_event(incident, policy_id))
        if command.action.value == "execute":
            return command, i
    raise AssertionError("no incident produced an execute command")


# ---------- end to end ----------

def test_handle_fault_runs_the_whole_loop_and_the_policy_learns():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("P", seed=1)

    outcomes = [layer.handle_fault(i, adapter, policy_id) for i in world.incidents]

    executed = [o for o in outcomes if o.result is not None]
    assert executed, "permissions must be derived from the registered candidates, otherwise the gate rejects everything"
    assert all(o.ack is not None for o in executed)
    state = layer.snapshot_policy(policy_id).selector_state
    assert sum(state["n"].values()) == sum(o.ack.policy_updated for o in executed) > 0


def test_candidates_can_be_seeded_from_yaml_and_only_when_the_registry_is_empty(tmp_path):
    db = f"sqlite:///{tmp_path / 'seed.db'}"
    yaml = CONFIGS / "candidates" / "default.yaml"
    assert len(ArcLayer(db, candidates=yaml).candidates()) == 6
    assert len(ArcLayer(db, candidates=yaml).candidates()) == 6  # a restart must not duplicate them


def test_learned_state_survives_a_restart(tmp_path):
    db = f"sqlite:///{tmp_path / 'learn.db'}"
    layer, world, adapter = _setup(db)
    policy_id = layer.create_policy("P", seed=1)
    for incident in world.incidents[:12]:
        layer.handle_fault(incident, adapter, policy_id)
    before = layer.snapshot_policy(policy_id).selector_state

    assert ArcLayer(db).snapshot_policy(policy_id).selector_state == before


# ---------- calling it from agent frameworks ----------

def test_policies_accept_overlapping_incidents_by_default_and_strict_mode_is_opt_in():
    layer, world, adapter = _setup()
    open_policy = layer.create_policy("P", seed=1)
    _first_execute(layer, adapter, world, open_policy)
    _first_execute(layer, adapter, world, open_policy)  # a second incident while the first has no result yet

    strict = layer.create_policy("P", seed=2, strict_sequential=True)
    _first_execute(layer, adapter, world, strict)
    with pytest.raises(PolicyBusy):
        layer.post_incident(adapter.to_fault_event(world.incidents[0], strict))


def test_concurrent_tasks_share_one_policy_without_losing_updates(tmp_path):
    layer, world, adapter = _setup(f"sqlite:///{tmp_path / 'conc.db'}", n_tasks=40)
    policy_id = layer.create_policy("P", seed=1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda i: layer.handle_fault(i, adapter, policy_id), world.incidents))

    updated = sum(bool(o.ack and o.ack.policy_updated) for o in outcomes)
    state = layer.snapshot_policy(policy_id).selector_state
    assert updated > 0 and sum(state["n"].values()) == updated


def test_async_hosts_can_await_handle_fault():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("P", seed=1)

    outcome = asyncio.run(layer.handle_fault_async(world.incidents[0], adapter, policy_id))

    assert outcome.command.incident_id


# ---------- a host that died with an incident in flight ----------

def test_incidents_orphaned_by_a_crash_are_censored_on_restart(tmp_path):
    db = f"sqlite:///{tmp_path / 'orphan.db'}"
    layer, world, adapter = _setup(db)
    policy_id = layer.create_policy("P", seed=1, strict_sequential=True)
    command, _ = _first_execute(layer, adapter, world, policy_id)
    # the host process dies here: the result is never reported

    restarted = ArcLayer(db)

    assert restarted.incident(command.incident_id).status == "censored"
    assert restarted.get_policy(policy_id).pending_incident_id is None


def test_orphan_censoring_on_start_can_be_turned_off(tmp_path):
    db = f"sqlite:///{tmp_path / 'keep.db'}"
    layer, world, adapter = _setup(db)
    policy_id = layer.create_policy("P", seed=1, strict_sequential=True)
    command, _ = _first_execute(layer, adapter, world, policy_id)

    kept = ArcLayer(db, censor_orphans_on_start=False)

    assert kept.incident(command.incident_id).status == "awaiting_result"


# ---------- behaviours carried over from the former HTTP tests ----------

def _result(command, answer="PASS"):
    return C.ExecutionResultIn(
        incident_id=command.incident_id, candidate_id=command.candidate_id, terminal=C.Terminal.TASK_COMPLETED,
        final_answer=answer, cost_used=0.1, tokens_used=10, latency_ms=100, actions_performed=[],
    )


def test_a_repeated_result_is_idempotent_and_a_different_payload_under_the_same_key_conflicts():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("P", seed=1)
    command, _ = _first_execute(layer, adapter, world, policy_id)
    result = _result(command)

    first = layer.post_result(result, "k1")

    assert layer.post_result(result, "k1") == first
    with pytest.raises(Conflict):
        layer.post_result(result.model_copy(update={"final_answer": "other"}), "k1")


def test_unknown_policy_and_incident_raise_not_found():
    layer, _, _ = _setup()
    with pytest.raises(NotFound):
        layer.get_policy("nope")
    with pytest.raises(NotFound):
        layer.incident("nope")


def test_policy_ids_are_unique_and_reward_weights_are_validated():
    layer, _, _ = _setup()
    layer.create_policy("P", seed=1, policy_id="fixed")
    with pytest.raises(Conflict):
        layer.create_policy("P", seed=1, policy_id="fixed")
    with pytest.raises(InvalidRewardWeights):
        layer.create_policy("P", seed=1, reward_weights=C.RewardWeightsIn(s=1, c=0.7, l=0.7, v=1))


def test_a_policy_refuses_incidents_embedded_with_a_different_model(tmp_path, monkeypatch):
    import numpy as np

    from arclayer.apiclients.embedding import sentence_transformer as st_mod

    class FakeModel:
        def encode(self, texts, **kw):
            return np.ones((len(texts), 4))

    db = f"sqlite:///{tmp_path / 'mismatch.db'}"
    layer, world, adapter = _setup(db)
    policy_id = layer.create_policy("P", seed=1)
    monkeypatch.setattr(st_mod, "_load_model", lambda name, device: FakeModel())

    other = ArcLayer(db, embedding="st:fake-model")

    with pytest.raises(FeatureMismatch):
        other.post_incident(adapter.to_fault_event(world.incidents[0], policy_id))


def test_a_frozen_policy_stops_learning():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("P", seed=1)
    assert layer.freeze_policy(policy_id).frozen is True

    outcomes = [layer.handle_fault(i, adapter, policy_id) for i in world.incidents[:10]]

    assert any(o.ack for o in outcomes)
    assert not any(o.ack.policy_updated for o in outcomes if o.ack)


def test_baseline_b0_always_stops_safely():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("B0", seed=1)
    command = layer.post_incident(adapter.to_fault_event(world.incidents[0], policy_id))
    assert command.action.value == "safe_stop"


def test_censor_expired_returns_the_ids_it_closed():
    layer, world, adapter = _setup()
    policy_id = layer.create_policy("P", seed=1, strict_sequential=True)
    command, _ = _first_execute(layer, adapter, world, policy_id)

    assert layer.censor_expired(ttl_s=0) == [command.incident_id]
    assert layer.censor_expired(ttl_s=0) == []


def test_a_disabled_candidate_is_left_out_of_policies_created_afterwards():
    layer, _, _ = _setup()
    target = layer.candidates()[0].candidate_id

    assert layer.set_candidate_enabled(target, False).enabled is False

    assert target not in layer.get_policy(layer.create_policy("P", seed=1)).candidate_ids


def test_ground_truth_never_appears_in_anything_the_host_can_read():
    secret = "TOP-SECRET-GROUND-TRUTH"
    world = SyntheticWorld(seed=3, n_tasks=30)
    layer = ArcLayer(None, candidates=synthetic_candidates())
    for task_id in world.oracle:
        layer.register_ground_truth(task_id, secret)
    adapter = SyntheticHostAdapter(world)
    policy_id = layer.create_policy("P", seed=1)
    command, _ = _first_execute(layer, adapter, world, policy_id)

    ack = layer.post_result(_result(command, answer="wrong"), "k")

    seen = [command, ack, layer.incident(command.incident_id), layer.get_policy(policy_id),
            layer.snapshot_policy(policy_id), *layer.candidates()]
    assert ack.status != "recovered" and ack.reward < 0  # a wrong answer is still scored against the hidden truth
    assert all(secret not in item.model_dump_json() for item in seen)
