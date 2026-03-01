import types

import pytest
from click.testing import CliRunner

from virl.cli.up.commands import _build_command, get_lab_title, start_lab, up


class _Node:
    def __init__(self, booted=True):
        self._booted = booted

    def is_booted(self):
        return self._booted


class _Lab:
    def __init__(self, lab_id="lab1", title="Lab One", active=False, nodes=None):
        self.id = lab_id
        self.title = title
        self._active = active
        self._nodes = nodes or [_Node(True)]
        self.wait_for_convergence = True
        self.started = False

    def is_active(self):
        return self._active

    def start(self):
        self.started = True
        self._active = True

    def nodes(self):
        return self._nodes


def _patch_up_core(monkeypatch, server, client):
    monkeypatch.setattr("virl.cli.up.commands.VIRLServer", lambda: server)
    monkeypatch.setattr("virl.cli.up.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab_by_title", lambda _t, _c: None)
    monkeypatch.setattr("virl.cli.up.commands.check_lab_cache", lambda _id: None)


def test_get_lab_title_build_command_and_start_lab(monkeypatch):
    # .virl path keeps basename
    assert get_lab_title("foo/bar/topology.virl") == "topology.virl"

    # non-.virl uses CachedLab title
    monkeypatch.setattr("virl.cli.up.commands.CachedLab", lambda _id, _f: types.SimpleNamespace(title="From YAML"))
    assert get_lab_title("topology.yaml") == "From YAML"

    # non-.virl with parse failure exits
    monkeypatch.setattr("virl.cli.up.commands.CachedLab", lambda _id, _f: (_ for _ in ()).throw(RuntimeError("bad")))
    with pytest.raises(SystemExit):
        get_lab_title("broken.yml")

    cmd = _build_command(["virl", "up"], True, False, f="topology.yaml", id="lab1", lab_name="Lab One")
    assert cmd == ["virl", "up", "-f", "topology.yaml", "--provision", "--no-start", "--id", "lab1", "--lab-name", "Lab One"]
    cmd = _build_command(["virl", "up"], False, True, f=None, id=None, lab_name=None)
    assert cmd == ["virl", "up", "--noprovision", "--start"]

    # start_lab with provisioning loop
    lab = _Lab(nodes=[_Node(False), _Node(True)])
    cached = []
    monkeypatch.setattr("virl.cli.up.commands.cache_lab", lambda _lab: cached.append(_lab.id))
    monkeypatch.setattr("virl.cli.up.commands.set_current_lab", lambda _id: cached.append(_id))
    monkeypatch.setattr("virl.cli.up.commands.time.sleep", lambda _s: None)
    nodes = lab._nodes

    def mark_booted():
        for n in nodes:
            n._booted = True
        return nodes

    monkeypatch.setattr(lab, "nodes", mark_booted)
    start_lab(lab, provision=True)
    assert lab.started is True
    assert cached == ["lab1", "lab1"]

    # Explicitly hit the not-booted break path before converging.
    lab2 = _Lab(nodes=[_Node(False)])
    calls = {"n": 0}

    def staged_nodes():
        calls["n"] += 1
        if calls["n"] > 1:
            lab2._nodes[0]._booted = True
        return lab2._nodes

    monkeypatch.setattr(lab2, "nodes", staged_nodes)
    start_lab(lab2, provision=True)


def test_up_current_lab_and_pull_paths(monkeypatch):
    server = types.SimpleNamespace(config={})
    client = types.SimpleNamespace(import_lab_from_path=lambda fname, title: _Lab(lab_id="new1", title=title))
    _patch_up_core(monkeypatch, server, client)
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: "cur1")

    current = _Lab(lab_id="cur1", title="Current", active=False)
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab", lambda _id, _c: current)
    cleared = []
    monkeypatch.setattr("virl.cli.up.commands.clear_current_lab", lambda: cleared.append(True))
    monkeypatch.setattr("virl.cli.up.commands.get_lab_title", lambda _f: "Imported")

    # clab exists + explicit file triggers warning clear and import path
    monkeypatch.setattr("virl.cli.up.commands.os.path.isfile", lambda p: p == "topology.yaml")
    out = CliRunner().invoke(up, ["--no-start", "-f", "topology.yaml"])
    assert out.exit_code == 0
    assert cleared

    # no found lab + file missing -> pull then recursive up
    calls = []

    def fake_call(cmd):
        calls.append(cmd)
        return 0

    monkeypatch.setattr("virl.cli.up.commands.call", fake_call)
    monkeypatch.setattr("virl.cli.up.commands.get_command", lambda: "virl")
    monkeypatch.setattr("virl.cli.up.commands.os.path.isfile", lambda _p: False)
    out = CliRunner().invoke(up, ["repo1", "-f", "topo.yaml"])
    assert out.exit_code == 0
    assert calls[0] == ["virl", "pull", "repo1", "--file", "topo.yaml"]
    assert calls[1][0:2] == ["virl", "up"]


def test_up_cache_eve_and_current_lab_branches(monkeypatch):
    server = types.SimpleNamespace(config={})
    imported = []

    def import_lab(fname, title):
        imported.append((fname, title))
        return _Lab(lab_id="imp1", title=title, active=True)

    client = types.SimpleNamespace(import_lab_from_path=import_lab)
    _patch_up_core(monkeypatch, server, client)
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: "cur2")
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab", lambda _id, _c: None if _id == "cur2" else None)
    monkeypatch.setattr("virl.cli.up.commands.check_lab_cache", lambda _id: "cached.yaml")
    monkeypatch.setattr("virl.cli.up.commands.get_lab_title", lambda _f: "Cached Title")
    monkeypatch.setattr("virl.cli.up.commands.cache_lab", lambda _lab: None)
    monkeypatch.setattr("virl.cli.up.commands.set_current_lab", lambda _id: None)

    # ID not on server but in cache -> imports cached file
    monkeypatch.setattr("virl.cli.up.commands.os.path.isfile", lambda p: p == "cached.yaml")
    out = CliRunner().invoke(up, ["--id", "missing-id"])
    assert out.exit_code == 0
    assert imported and imported[0][0] == "cached.yaml"

    # ID missing from both server and cache, continue to lab-name lookup path.
    monkeypatch.setattr("virl.cli.up.commands.check_lab_cache", lambda _id: None)
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab_by_title", lambda _t, _c: _Lab(lab_id="by-name", title="ByName"))
    out = CliRunner().invoke(up, ["--id", "missing-id", "--lab-name", "ByName", "--no-start"])
    assert out.exit_code == 0

    # Alt .virl fallback path when topology.yaml is missing.
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: None)
    monkeypatch.setattr(
        "virl.cli.up.commands.os.path.isfile",
        lambda p: p == "topology.virl",
    )
    monkeypatch.setattr("virl.cli.up.commands.get_lab_title", lambda _f: "VIRL Title")
    out = CliRunner().invoke(up, ["--no-start"])
    assert out.exit_code == 0

    # .unl conversion failure exits with rc
    monkeypatch.setattr("virl.cli.up.commands.check_lab_cache", lambda _id: None)
    monkeypatch.setattr("virl.cli.up.commands.os.path.isfile", lambda p: p == "lab.unl")
    monkeypatch.setattr("virl.cli.up.commands.call", lambda _cmd: 3)
    out = CliRunner().invoke(up, ["--no-start", "-f", "lab.unl"])
    assert out.exit_code == 3

    # .unl conversion missing converter (FileNotFoundError path)
    monkeypatch.setattr("virl.cli.up.commands.call", lambda _cmd: (_ for _ in ()).throw(FileNotFoundError()))
    out = CliRunner().invoke(up, ["--no-start", "-f", "lab.unl"])
    assert out.exit_code == -1

    # .unl conversion success path updates fname to .yaml
    monkeypatch.setattr("virl.cli.up.commands.call", lambda _cmd: 0)
    monkeypatch.setattr("virl.cli.up.commands.get_lab_title", lambda f: f)
    out = CliRunner().invoke(up, ["--no-start", "-f", "lab.unl"])
    assert out.exit_code == 0
    assert imported[-1][0].endswith(".yaml")

    # current lab already set branch with start on inactive lab
    clab = _Lab(lab_id="cur3", title="Current3", active=False)
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: "cur3")
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab", lambda _id, _c: clab)
    started = []
    monkeypatch.setattr("virl.cli.up.commands.start_lab", lambda lab, provision=False: started.append((lab.id, provision)))
    out = CliRunner().invoke(up, [])
    assert out.exit_code == 0
    assert started == [("cur3", False)]

    # current lab set + no-start skips start_lab call
    out = CliRunner().invoke(up, ["--no-start"])
    assert out.exit_code == 0

    # repo argument empty string skips pull fallback and reaches generic error path.
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: None)
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab", lambda _id, _c: None)
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab_by_title", lambda _t, _c: None)
    monkeypatch.setattr("virl.cli.up.commands.os.path.isfile", lambda _p: False)
    out = CliRunner().invoke(up, [""], catch_exceptions=False)
    assert out.exit_code == 1

    # clab already active should not call start_lab.
    clab_active = _Lab(lab_id="cur4", title="Current4", active=True)
    monkeypatch.setattr("virl.cli.up.commands.get_current_lab", lambda: "cur4")
    monkeypatch.setattr("virl.cli.up.commands.safe_join_existing_lab", lambda _id, _c: clab_active)
    started.clear()
    out = CliRunner().invoke(up, [])
    assert out.exit_code == 0
    assert started == []
