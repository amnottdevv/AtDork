"""
Unit tests for the workflow engine (core/workflow.py) and its CLI wiring
(atdork.workflow_cli / --run-workflow).

Network is never touched: run_batch is monkeypatched at the core.workflow
namespace with a recording fake. HOME is patched so the state directory
(~/.atdork/state/workflows) never leaks outside tmp_path.
"""

import json
from pathlib import Path

import pytest
import yaml

import core.workflow as wf_mod
from core.workflow import (
    WORKFLOW_FILENAMES,
    WorkflowEngine,
    WorkflowError,
    WorkflowRun,
    collect_workflows,
    discover_workflow_files,
    load_workflow_file,
    substitute,
    validate_workflow,
)
from core.config import _CURRENT, override_setting
from core.env import create_env


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Registry + config state never leak between tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ATDORK_ENV", raising=False)
    _CURRENT.clear()
    yield
    _CURRENT.clear()


def make_wf(**overrides):
    """Minimal valid workflow definition."""
    wf = {
        "target": "example.com",
        "steps": [{"name": "s1", "query": "site:{target} a"}],
    }
    wf.update(overrides)
    return wf


def default_result(query):
    return [{"href": f"https://results.invalid/{abs(hash(query))}", "title": query}]


def install_fake_run_batch(monkeypatch, results_by_query=None, fail_queries=()):
    """Replace run_batch with a recording fake; returns the call log."""
    calls = []

    def fake(queries, case_modules=None, concurrency=1, *, cache=None,
             on_query_done=None, **kwargs):
        calls.append({"queries": list(queries), "concurrency": concurrency,
                      "kwargs": kwargs, "case_modules": case_modules})
        out = {}
        for q in queries:
            if q in fail_queries:
                res, ok = [], False
            else:
                res = (results_by_query or {}).get(q) or default_result(q)
                ok = True
            out[q] = res
            if on_query_done:
                on_query_done(q, res, ok)
        return out

    monkeypatch.setattr(wf_mod, "run_batch", fake)
    return calls


# ── substitute() ───────────────────────────────────────────────────────────

def test_substitute_known_tokens():
    ctx = {"target": "example.com", "step": "s1", "date": "20261017", "run_id": "abc"}
    assert substitute("site:{target} {step} {date} {run_id}", ctx) == \
        "site:example.com s1 20261017 abc"


def test_substitute_unknown_token_left_intact():
    assert substitute("x {unknown} y", {"target": "t"}) == "x {unknown} y"


def test_substitute_literal_braces_untouched():
    # Non-word tokens (Google OR-groups) are never substitution candidates.
    assert substitute("ext:{pdf,docx}", {"target": "t"}) == "ext:{pdf,docx}"


def test_substitute_non_string_passthrough():
    assert substitute(42, {"target": "t"}) == 42


# ── validate_workflow() ────────────────────────────────────────────────────

def test_validate_minimal_valid():
    assert validate_workflow("wf", make_wf()) == []


def test_validate_not_a_mapping():
    assert "must be a mapping" in validate_workflow("wf", [1, 2])[0]


def test_validate_missing_steps():
    errors = validate_workflow("wf", {"target": "x"})
    assert any("steps" in e and "non-empty list" in e for e in errors)


def test_validate_empty_steps():
    errors = validate_workflow("wf", {"steps": []})
    assert any("non-empty list" in e for e in errors)


def test_validate_step_missing_query():
    errors = validate_workflow("wf", {"target": "x", "steps": [{"name": "s"}]})
    assert any("requires 'query' or 'queries'" in e for e in errors)


def test_validate_query_and_queries_mutually_exclusive():
    step = {"name": "s", "query": "a", "queries": ["b"]}
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("mutually exclusive" in e for e in errors)


def test_validate_unknown_workflow_key():
    errors = validate_workflow("wf", make_wf(bogus=1))
    assert any("unknown key(s): bogus" in e for e in errors)


def test_validate_unknown_step_key():
    definition = make_wf(steps=[{"name": "s", "query": "q", "oops": True}])
    errors = validate_workflow("wf", definition)
    assert any("unknown key(s): oops" in e for e in errors)


def test_validate_duplicate_step_names():
    definition = make_wf(steps=[
        {"name": "s", "query": "q1"}, {"name": "s", "query": "q2"},
    ])
    errors = validate_workflow("wf", definition)
    assert any("duplicate step name 's'" in e for e in errors)


def test_validate_default_step_names_are_unique():
    definition = {"target": "x", "steps": [{"query": "q1"}, {"query": "q2"}]}
    assert validate_workflow("wf", definition) == []


def test_validate_retry_with_requires_threshold():
    step = {"name": "s", "query": "q", "retry_with": ["r"]}
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("retry_with requires when_results_below" in e for e in errors)


def test_validate_when_results_below_type():
    step = {"name": "s", "query": "q", "when_results_below": "five"}
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("when_results_below must be an integer" in e for e in errors)


def test_validate_on_error_values():
    errors = validate_workflow("wf", make_wf(on_error="explode"))
    assert any("on_error" in e for e in errors)
    assert validate_workflow("wf", make_wf(on_error="continue")) == []


def test_validate_outputs_shape():
    step = {"name": "s", "query": "q",
            "outputs": [{"format": "json"}]}  # no file
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("'file' is required" in e for e in errors)

    step = {"name": "s", "query": "q",
            "outputs": [{"file": "a.txt", "format": "xml"}]}
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("format must be one of" in e for e in errors)

    step = {"name": "s", "query": "q", "outputs": [{"file": "a", "extra": 1}]}
    errors = validate_workflow("wf", {"target": "x", "steps": [step]})
    assert any("unknown key(s): extra" in e for e in errors)


def test_validate_target_token_without_target():
    definition = {"steps": [{"name": "s", "query": "site:{target} x"}]}
    errors = validate_workflow("wf", definition)
    assert any("use {target}" in e for e in errors)


def test_validate_target_override_satisfies_token():
    definition = {"steps": [{"name": "s", "query": "site:{target} x"}]}
    assert validate_workflow("wf", definition, target="example.org") == []


def test_validate_unknown_substitution_token():
    definition = make_wf(steps=[{"name": "s", "query": "site:{target} {targt}"}])
    errors = validate_workflow("wf", definition)
    assert any("unknown substitution '{targt}'" in e for e in errors)


def test_validate_workers_range():
    assert validate_workflow("wf", make_wf(workers=0))
    assert validate_workflow("wf", make_wf(workers=65))
    assert validate_workflow("wf", make_wf(workers=2)) == []


def test_validate_worker_overrides_unknown_key():
    assert validate_workflow("wf", make_wf(worker_overrides={"nope": 1}))
    assert validate_workflow("wf", make_wf(worker_overrides={"backend": "serper"})) == []


def test_validate_search_key_types():
    assert validate_workflow("wf", make_wf(max_results="many"))
    assert validate_workflow("wf", make_wf(max_results=25)) == []


# ── Discovery & file loading ───────────────────────────────────────────────

def _write_workflow_file(directory, name, workflows):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(yaml.safe_dump({"workflows": workflows}), encoding="utf-8")
    return path


def test_discover_finds_workflow_yaml_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_workflow_file(tmp_path, "workflow.yaml", make_wf())
    assert discover_workflow_files() == [path]


def test_discover_all_filenames_supported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for filename in WORKFLOW_FILENAMES:
        (tmp_path / filename).write_text("workflows: {}", encoding="utf-8")
    assert len(discover_workflow_files()) == len(WORKFLOW_FILENAMES)


def test_discover_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert discover_workflow_files() == []


def test_discover_env_root_wins_over_cwd(tmp_path, monkeypatch):
    """Merged later-wins: the env root file overrides the CWD one."""
    monkeypatch.chdir(tmp_path)
    env = create_env(tmp_path / "ws", name="demo")
    _write_workflow_file(tmp_path, "workflow.yaml",
                         {"shared": make_wf(target="cwd.example")})
    _write_workflow_file(env.root, "workflow.yaml",
                         {"shared": make_wf(target="env.example")})
    collected = collect_workflows(discover_workflow_files(env))
    assert collected["shared"][0]["target"] == "env.example"


def test_load_workflow_file_with_workflows_key(tmp_path):
    path = _write_workflow_file(tmp_path, "a.yml", {"demo": make_wf()})
    workflows = load_workflow_file(path)
    assert set(workflows) == {"demo"}
    assert workflows["demo"]["target"] == "example.com"


def test_load_workflow_file_bare_mapping(tmp_path):
    path = tmp_path / "bare.yml"
    path.write_text(yaml.safe_dump({"demo": make_wf()}), encoding="utf-8")
    workflows = load_workflow_file(path)
    assert set(workflows) == {"demo"}


def test_load_workflow_file_missing(tmp_path):
    with pytest.raises(WorkflowError, match="not found"):
        load_workflow_file(tmp_path / "nope.yml")


def test_load_workflow_file_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text("workflows: [unclosed", encoding="utf-8")
    with pytest.raises(WorkflowError, match="Invalid YAML"):
        load_workflow_file(path)


def test_load_workflow_file_wrong_shape(tmp_path):
    path = tmp_path / "shape.yml"
    path.write_text("just: 42\n", encoding="utf-8")
    with pytest.raises(WorkflowError, match="workflows"):
        load_workflow_file(path)


def test_load_workflow_file_empty(tmp_path):
    path = tmp_path / "empty.yml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(WorkflowError, match="empty"):
        load_workflow_file(path)


def test_collect_file_overrides_config(tmp_path):
    path = _write_workflow_file(tmp_path, "a.yml",
                                {"wf": make_wf(target="file.example")})
    collected = collect_workflows([path], {"wf": make_wf(target="config.example")})
    assert collected["wf"][0]["target"] == "file.example"
    assert collected["wf"][1] == str(path)


def test_collect_merges_distinct_names(tmp_path):
    path = _write_workflow_file(tmp_path, "a.yml", {"from-file": make_wf()})
    collected = collect_workflows([path], {"from-config": make_wf()})
    assert set(collected) == {"from-file", "from-config"}
    assert collected["from-config"][1] == "config"


# ── WorkflowRun (state) ────────────────────────────────────────────────────

def test_state_save_load_roundtrip(tmp_path):
    state = WorkflowRun("wf", tmp_path / "wf.json")
    state.mark_step("s1", {"status": "done", "results": 7})
    state.save()
    loaded = WorkflowRun.load("wf", tmp_path / "wf.json")
    assert loaded.run_id == state.run_id
    assert loaded.step_status("s1") == "done"
    assert loaded.data["steps"]["s1"]["results"] == 7


def test_state_corrupt_file_starts_fresh(tmp_path):
    path = tmp_path / "wf.json"
    path.write_text("{corrupt", encoding="utf-8")
    loaded = WorkflowRun.load("wf", path)
    assert loaded.data["steps"] == {}
    assert loaded.run_id


def test_state_missing_file_starts_fresh(tmp_path):
    loaded = WorkflowRun.load("wf", tmp_path / "absent.json")
    assert loaded.data["status"] == "running"


# ── WorkflowEngine: execution semantics ────────────────────────────────────

def test_engine_sequential_step_order(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    definition = make_wf(steps=[
        {"name": "first", "query": "q-one"},
        {"name": "second", "query": "q-two"},
    ])
    summary = WorkflowEngine("wf", definition).run()
    assert [c["queries"] for c in calls] == [["q-one"], ["q-two"]]
    assert [s["name"] for s in summary["steps"]] == ["first", "second"]
    assert summary["status"] == "completed"


def test_engine_substitutes_target_in_executed_queries(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    WorkflowEngine("wf", make_wf()).run()
    assert calls[0]["queries"] == ["site:example.com a"]


def test_engine_cli_target_overrides_definition(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    WorkflowEngine("wf", make_wf(), target="other.example").run()
    assert calls[0]["queries"] == ["site:other.example a"]


def test_engine_threshold_triggers_retry_and_dedupes(monkeypatch):
    shared = {"href": "https://same.invalid/", "title": "shared"}
    extra = {"href": "https://extra.invalid/", "title": "extra"}
    results = {"big": [dict(shared)],
               "r1": [dict(shared), dict(extra)],
               "r2": [{"href": "https://third.invalid/", "title": "third"}]}
    calls = install_fake_run_batch(monkeypatch, results_by_query=results)
    definition = make_wf(steps=[{
        "name": "s1", "query": "big", "when_results_below": 5,
        "retry_with": ["r1", "r2"],
    }])
    summary = WorkflowEngine("wf", definition).run()
    assert len(calls) == 2
    assert calls[1]["queries"] == ["r1", "r2"]
    # shared href counted once → 3 unique ≥ threshold 5? No: 3 < 5 → below.
    step = summary["steps"][0]
    assert step["below_threshold"] is True
    assert step["status"] == "below_threshold"
    assert step["results"] == 3


def test_engine_no_retry_when_threshold_met(monkeypatch):
    results = {"big": [{"href": f"https://x/{i}.invalid/", "title": str(i)}
                       for i in range(5)]}
    calls = install_fake_run_batch(monkeypatch, results_by_query=results)
    definition = make_wf(steps=[{
        "name": "s1", "query": "big", "when_results_below": 5,
        "retry_with": ["never-run"],
    }])
    summary = WorkflowEngine("wf", definition).run()
    assert len(calls) == 1
    assert summary["steps"][0]["status"] == "done"


def test_engine_all_queries_failed_stops_run(monkeypatch):
    calls = install_fake_run_batch(monkeypatch, fail_queries={"broken"})
    definition = make_wf(steps=[
        {"name": "bad", "query": "broken"},
        {"name": "good", "query": "ok"},
    ])
    summary = WorkflowEngine("wf", definition).run()
    assert summary["status"] == "failed"
    assert len(calls) == 1  # second step never ran
    assert summary["steps"][0]["status"] == "failed"
    assert "all 1 queries failed" in summary["steps"][0]["error"]


def test_engine_on_error_continue_runs_next_step(monkeypatch):
    calls = install_fake_run_batch(monkeypatch, fail_queries={"broken"})
    definition = make_wf(steps=[
        {"name": "bad", "query": "broken", "on_error": "continue"},
        {"name": "good", "query": "ok"},
    ])
    summary = WorkflowEngine("wf", definition).run()
    assert summary["status"] == "completed"
    assert [c["queries"] for c in calls] == [["broken"], ["ok"]]
    assert summary["steps"][0]["status"] == "failed"


def test_engine_resume_skips_completed_steps(monkeypatch, tmp_path):
    definition = make_wf(steps=[
        {"name": "one", "query": "q1"},
        {"name": "two", "query": "q2"},
    ])
    install_fake_run_batch(monkeypatch)
    first = WorkflowEngine("wf", definition).run()
    assert first["status"] == "completed"

    calls = install_fake_run_batch(monkeypatch)
    resumed = WorkflowEngine("wf", definition).run(resume=True)
    assert calls == []  # both steps were done → nothing re-ran
    assert all(s.get("skipped") for s in resumed["steps"])
    assert resumed["run_id"] == first["run_id"]


def test_engine_resume_reruns_failed_steps(monkeypatch):
    definition = make_wf(steps=[{"name": "bad", "query": "broken"}])
    install_fake_run_batch(monkeypatch, fail_queries={"broken"})
    first = WorkflowEngine("wf", definition).run()
    assert first["status"] == "failed"

    calls = install_fake_run_batch(monkeypatch)
    resumed = WorkflowEngine("wf", definition).run(resume=True)
    assert len(calls) == 1  # failed step re-ran
    assert resumed["status"] == "completed"


def test_engine_fresh_run_overwrites_state(monkeypatch):
    definition = make_wf(steps=[{"name": "one", "query": "q"}])
    install_fake_run_batch(monkeypatch)
    first = WorkflowEngine("wf", definition).run()
    calls = install_fake_run_batch(monkeypatch)
    second = WorkflowEngine("wf", definition).run()
    assert len(calls) == 1
    assert second["run_id"] != first["run_id"]


def test_engine_dry_run_never_searches_nor_writes(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not execute searches")
    monkeypatch.setattr(wf_mod, "run_batch", forbidden)
    definition = make_wf(steps=[
        {"name": "s1", "query": "site:{target} a",
         "when_results_below": 3, "retry_with": ["alt"]},
    ])
    engine = WorkflowEngine("wf", definition)
    summary = engine.run(dry_run=True)
    assert summary["dry_run"] is True
    assert summary["steps"][0]["status"] == "planned"
    assert summary["steps"][0]["queries"] == ["site:example.com a"]
    assert summary["steps"][0]["retry_with"] == ["alt"]
    assert not engine.state_file().exists()


def test_engine_workers_forwarded_to_run_batch(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    WorkflowEngine("wf", make_wf(workers=3)).run()
    assert calls[0]["concurrency"] == 3


def test_engine_cli_workers_override_definition(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    WorkflowEngine("wf", make_wf(workers=2), workers=5).run()
    assert calls[0]["concurrency"] == 5


def test_engine_worker_overrides_merged_into_kwargs(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    definition = make_wf(
        backend="auto", max_results=10,
        worker_overrides={"backend": "serper"},
        steps=[
            {"name": "s1", "query": "q1",
             "worker_overrides": {"backend": "brave"}},
            {"name": "s2", "query": "q2"},
        ],
    )
    WorkflowEngine("wf", definition).run()
    assert calls[0]["kwargs"]["backend"] == "brave"   # step overlay wins
    assert calls[1]["kwargs"]["backend"] == "serper"  # workflow overlay
    assert calls[0]["kwargs"]["max_results"] == 10    # workflow default


def test_engine_case_modules_built_with_fallback(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    WorkflowEngine("wf", make_wf()).run()
    modules = calls[0]["case_modules"]
    assert modules["circuit_breaker"] is not None
    assert modules["fallback_manager"] is not None
    assert modules["retry_handler"] is not None


def test_engine_outputs_written_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_fake_run_batch(monkeypatch)
    definition = make_wf(steps=[{
        "name": "s1", "query": "q",
        "outputs": [{"file": "out/s1.json", "format": "json"}],
    }])
    summary = WorkflowEngine("wf", definition).run()
    out = tmp_path / "out" / "s1.json"
    assert summary["steps"][0]["outputs"] == [str(out)]
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload


def test_engine_outputs_relative_resolve_into_env(tmp_path, monkeypatch):
    env = create_env(tmp_path / "ws", name="demo")

    def fake(queries, case_modules=None, concurrency=1, *, cache=None,
             on_query_done=None, **kwargs):
        out = {q: default_result(q) for q in queries}
        if on_query_done:
            for q in queries:
                on_query_done(q, out[q], True)
        return out

    monkeypatch.setattr(wf_mod, "run_batch", fake)
    definition = make_wf(steps=[{
        "name": "s1", "query": "q",
        "outputs": [{"file": "nested/res.json", "format": "json"}],
    }])
    summary = WorkflowEngine("wf", definition, workspace=env).run()
    written = Path(summary["steps"][0]["outputs"][0])
    assert str(written).startswith(str(env.results_dir))
    assert written.is_file()


def test_engine_output_escaping_env_is_rejected(tmp_path, monkeypatch):
    env = create_env(tmp_path / "ws", name="demo")

    def fake(queries, case_modules=None, concurrency=1, *, cache=None,
             on_query_done=None, **kwargs):
        out = {q: default_result(q) for q in queries}
        if on_query_done:
            for q in queries:
                on_query_done(q, out[q], True)
        return out

    monkeypatch.setattr(wf_mod, "run_batch", fake)
    definition = make_wf(steps=[{
        "name": "s1", "query": "q",
        "outputs": [{"file": "/etc/passwd-wannabe", "format": "txt"}],
    }])
    # A step-level WorkflowError is recorded (on_error applies), not raised:
    # the guard violation fails the step and stops the run by default.
    summary = WorkflowEngine("wf", definition, workspace=env).run()
    assert summary["status"] == "failed"
    assert "escapes the environment" in summary["steps"][0]["error"]


def test_engine_state_file_lives_in_env(tmp_path):
    env = create_env(tmp_path / "ws", name="demo")
    engine = WorkflowEngine("wf", make_wf(), workspace=env)
    assert engine.state_file() == env.state_dir / "workflows" / "wf.json"


def test_engine_only_step_filter(monkeypatch):
    calls = install_fake_run_batch(monkeypatch)
    definition = make_wf(steps=[
        {"name": "one", "query": "q1"},
        {"name": "two", "query": "q2"},
    ])
    summary = WorkflowEngine("wf", definition).run(only_step="two")
    assert [c["queries"] for c in calls] == [["q2"]]
    assert len(summary["steps"]) == 1


def test_engine_unknown_step_filter_raises():
    engine = WorkflowEngine("wf", make_wf())
    with pytest.raises(WorkflowError, match="Unknown step"):
        engine.run(only_step="ghost")


def test_engine_invalid_definition_raises():
    with pytest.raises(WorkflowError, match="Invalid workflow"):
        WorkflowEngine("wf", {"steps": []}).run()


def test_engine_validate_reports_target_gap():
    definition = {"steps": [{"name": "s", "query": "site:{target} x"}]}
    errors = WorkflowEngine("wf", definition).validate()
    assert any("use {target}" in e for e in errors)


# ── CLI wiring (atdork.workflow_cli / --run-workflow) ──────────────────────

def _write_root_workflow(tmp_path, monkeypatch, workflows=("demo",)):
    data = {"workflows": {name: make_wf() for name in workflows}}
    (tmp_path / "workflow.yaml").write_text(
        yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)


def test_workflow_cli_list(tmp_path, monkeypatch, capsys):
    from atdork import workflow_cli
    _write_root_workflow(tmp_path, monkeypatch)
    rc = workflow_cli(["list"])
    assert rc == 0
    assert "demo" in capsys.readouterr().out


def test_workflow_cli_list_shows_config_workflows(tmp_path, monkeypatch, capsys):
    from atdork import workflow_cli
    monkeypatch.chdir(tmp_path)
    override_setting("workflows", {"from-config": make_wf()})
    rc = workflow_cli(["list"])
    assert rc == 0
    assert "from-config" in capsys.readouterr().out


def test_workflow_cli_validate_ok(tmp_path, monkeypatch, capsys):
    from atdork import workflow_cli
    _write_root_workflow(tmp_path, monkeypatch)
    assert workflow_cli(["validate"]) == 0
    assert "valid" in capsys.readouterr().out


def test_workflow_cli_validate_invalid_returns_1(tmp_path, monkeypatch):
    from atdork import workflow_cli
    bad = {"workflows": {"broken": {"steps": [{"name": "s"}]}}}
    (tmp_path / "workflow.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert workflow_cli(["validate"]) == 1


def test_workflow_cli_run_dry(tmp_path, monkeypatch, capsys):
    from atdork import workflow_cli
    _write_root_workflow(tmp_path, monkeypatch)
    rc = workflow_cli(["run", "demo", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "site:example.com a" in out
    assert "Workflow completed" in out


def test_workflow_cli_run_unknown_name(tmp_path, monkeypatch):
    from atdork import workflow_cli
    _write_root_workflow(tmp_path, monkeypatch)
    assert workflow_cli(["run", "ghost"]) == 1


def test_run_workflow_flag_resolves_root_dot(tmp_path, monkeypatch):
    from atdork import _resolve_workflow
    _write_root_workflow(tmp_path, monkeypatch)
    name, definition, source = _resolve_workflow(".", None)
    assert name == "demo"
    assert Path(source).name == "workflow.yaml"


def test_run_workflow_flag_resolves_explicit_file(tmp_path, monkeypatch):
    from atdork import _resolve_workflow
    monkeypatch.chdir(tmp_path)
    path = _write_workflow_file(tmp_path, "custom.yml", {"solo": make_wf()})
    name, definition, source = _resolve_workflow(str(path), None)
    assert (name, source) == ("solo", str(path))


def test_resolve_workflow_dot_multiple_errors(tmp_path, monkeypatch):
    from atdork import _resolve_workflow
    _write_root_workflow(tmp_path, monkeypatch, workflows=("one", "two"))
    with pytest.raises(WorkflowError, match="pick one"):
        _resolve_workflow(".", None)


def test_resolve_workflow_file_multiple_errors(tmp_path, monkeypatch):
    from atdork import _resolve_workflow
    monkeypatch.chdir(tmp_path)
    path = _write_workflow_file(tmp_path, "multi.yml",
                                {"a": make_wf(), "b": make_wf()})
    with pytest.raises(WorkflowError, match="pass the name explicitly"):
        _resolve_workflow(str(path), None)


def test_workflow_cli_no_args_prints_help(capsys):
    from atdork import workflow_cli
    assert workflow_cli([]) == 1


def test_run_workflow_end_to_end_with_env(tmp_path, monkeypatch, capsys):
    """Full path: root workflow.yaml + active env → run --dry-run, no leaks."""
    from atdork import workflow_cli
    env = create_env(tmp_path / "ws", name="demo")
    (env.root / "workflow.yaml").write_text(
        yaml.safe_dump({"workflows": {"demo": make_wf()}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # CWD outside the env root
    rc = workflow_cli(["run", "demo", "--dry-run"], workspace=env)
    assert rc == 0
    assert "site:example.com a" in capsys.readouterr().out
    assert not (env.state_dir / "workflows").exists()  # dry-run writes nothing
