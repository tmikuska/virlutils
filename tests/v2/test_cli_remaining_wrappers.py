import types

from click.testing import CliRunner

from virl.api import NoPluginError
from virl.cli.extract.commands import extract
from virl.cli.license import license as license_group
from virl.cli.license.features import features as features_group
from virl.cli.license.renew import renew as renew_group
from virl.cli.ls.commands import ls
from virl.cli.nodes.commands import nodes
from virl.cli.use.commands import check_lab_cache_server, use


def _install_viewer(monkeypatch, module_path, rendered):
    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr(f"{module_path}.ViewerPlugin", lambda **_kwargs: _Viewer())


class _Client:
    def __init__(self):
        self.user_management = types.SimpleNamespace(users=lambda: [{"id": "u1", "username": "alice"}])

    def get_lab_list(self, all_users=False):
        return ["lab1"]

    def join_existing_lab(self, lab_id):
        return types.SimpleNamespace(
            id=lab_id,
            title="Lab One",
            owner="u1",
            state=lambda: "BOOTED",
            statistics={"nodes": 1, "links": 0, "interfaces": 1},
        )

    def get_system_health(self):
        return {"computes": {"c1": {"hostname": "h1"}}}


def test_license_feature_and_renew_groups_execute():
    license_group.callback()
    features_group.callback()
    renew_group.callback()


def test_extract_command_paths(monkeypatch):
    lab = types.SimpleNamespace(id="lab1")
    monkeypatch.setattr("virl.cli.extract.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.extract.commands.get_cml_client", lambda _s: _Client())
    monkeypatch.setattr("virl.cli.extract.commands.get_current_lab", lambda: "lab1")
    monkeypatch.setattr("virl.cli.extract.commands.safe_join_existing_lab", lambda _id, _c: lab)
    called = []
    monkeypatch.setattr("virl.cli.extract.commands.extract_configurations", lambda _l: called.append("extract"))
    monkeypatch.setattr("virl.cli.extract.commands.cache_lab", lambda _l, force=True: called.append("cache"))
    assert CliRunner().invoke(extract, []).exit_code == 0
    assert called == ["extract", "cache"]
    assert CliRunner().invoke(extract, ["--no-update-cache"]).exit_code == 0
    monkeypatch.setattr("virl.cli.extract.commands.safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(extract, []).exit_code == 1
    monkeypatch.setattr("virl.cli.extract.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(extract, []).exit_code == 1


def test_ls_nodes_and_use_paths(monkeypatch):
    client = _Client()
    monkeypatch.setattr("virl.cli.ls.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.ls.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.ls.commands.get_cache_root", lambda: "/tmp/no-cache")
    monkeypatch.setattr("virl.cli.ls.commands.os.path.isdir", lambda _p: False)
    monkeypatch.setattr(
        "virl.cli.ls.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    monkeypatch.setattr("virl.cli.ls.commands.lab_list_table", lambda *_args, **_kwargs: None)
    assert CliRunner().invoke(ls, []).exit_code == 0
    rendered = []
    _install_viewer(monkeypatch, "virl.cli.ls.commands", rendered)
    assert CliRunner().invoke(ls, ["--all"]).exit_code == 0
    assert rendered

    lab = types.SimpleNamespace(
        nodes=lambda: [],
        sync_operational_if_outdated=lambda: None,
    )
    monkeypatch.setattr("virl.cli.nodes.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.nodes.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.nodes.commands.get_current_lab", lambda: "lab1")
    monkeypatch.setattr("virl.cli.nodes.commands.safe_join_existing_lab", lambda _id, _c: lab)
    monkeypatch.setattr(
        "virl.cli.nodes.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(nodes, []).exit_code == 0
    rendered = []
    _install_viewer(monkeypatch, "virl.cli.nodes.commands", rendered)
    assert CliRunner().invoke(nodes, []).exit_code == 0
    assert rendered and "nodes" in rendered[0]
    monkeypatch.setattr("virl.cli.nodes.commands.safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(nodes, []).exit_code == 1
    monkeypatch.setattr("virl.cli.nodes.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(nodes, []).exit_code == 1

    # use command helper and paths
    monkeypatch.setattr("virl.cli.use.commands.check_lab_cache", lambda _id: None)
    monkeypatch.setattr("virl.cli.use.commands.safe_join_existing_lab", lambda _id, _c: types.SimpleNamespace(id=_id))
    cached = []
    monkeypatch.setattr("virl.cli.use.commands.cache_lab", lambda _lab: cached.append(True))
    assert check_lab_cache_server("lab1", client) == "lab1"
    assert cached == [True]

    monkeypatch.setattr("virl.cli.use.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.use.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.use.commands.get_command", lambda: "virl")
    monkeypatch.setattr("virl.cli.use.commands.call", lambda _cmd: 0)
    monkeypatch.setattr("virl.cli.use.commands.check_lab_cache_server", lambda _id, _c: "lab1")
    monkeypatch.setattr("virl.cli.use.commands.safe_join_existing_lab_by_title", lambda _lab, _c: types.SimpleNamespace(id="lab2"))
    set_calls = []
    monkeypatch.setattr("virl.cli.use.commands.set_current_lab", lambda lab_id: set_calls.append(lab_id))
    assert CliRunner().invoke(use, ["--id", "lab1"]).exit_code == 0
    assert CliRunner().invoke(use, ["--lab-name", "Lab One"]).exit_code == 0
    assert set_calls == ["lab1", "lab1"]
    monkeypatch.setattr("virl.cli.use.commands.safe_join_existing_lab_by_title", lambda _lab, _c: None)
    assert CliRunner().invoke(use, ["--lab-name", "Missing Lab"]).exit_code == 1
    assert CliRunner().invoke(use, []).exit_code == 0
