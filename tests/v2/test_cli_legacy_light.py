import types

from click.testing import CliRunner

from virl.api import NoPluginError
from virl.cli.cluster.info import commands as cluster_info_commands
from virl.cli.clear.commands import clear
from virl.cli.groups.delete.commands import delete_groups
from virl.cli.groups.ls.commands import list_groups
from virl.cli.groups.update.commands import update_groups
from virl.cli.id.commands import lid
from virl.cli.search.commands import search


def _install_viewer(monkeypatch, module_path, rendered):
    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr(f"{module_path}.ViewerPlugin", lambda **_kwargs: _Viewer())


class _UserMgmt:
    def users(self):
        return [{"id": "u1", "username": "alice"}, {"id": "u2", "username": "bob"}]


class _GroupMgmt:
    def __init__(self):
        self.deleted = []
        self.updated = []

    def groups(self):
        return [
            {
                "id": "g1",
                "name": "group1",
                "description": "desc",
                "members": ["u1"],
                "associations": [{"id": "l1", "permissions": ["lab_view"]}],
            },
            {
                "id": "g2",
                "name": "group2",
                "description": "desc",
                "members": ["u2"],
                "associations": [{"id": "l2", "permissions": ["lab_view"]}],
            },
        ]

    def delete_group(self, gid):
        self.deleted.append(gid)

    def update_group(self, **kwargs):
        self.updated.append(kwargs)


class _Client:
    def __init__(self):
        self.user_management = _UserMgmt()
        self.group_management = _GroupMgmt()

    def all_labs(self, show_all=True):
        return [types.SimpleNamespace(id="l1", title="Lab One"), types.SimpleNamespace(id="l2", title="Lab Two")]

    def get_system_health(self):
        return {
            "computes": {
                "c1": {
                    "hostname": "host1",
                    "is_controller": True,
                    "kvm_vmx_enabled": True,
                    "enough_cpus": True,
                    "refplat_images_available": True,
                    "lld_connected": True,
                    "valid": True,
                }
            }
        }

    def get_lab_list(self):
        return ["lab1"]

    def join_existing_lab(self, lab_id):
        return types.SimpleNamespace(title="Lab One", id=lab_id)


def test_clear_invokes_clear_current_lab(monkeypatch):
    called = []
    monkeypatch.setattr("virl.cli.clear.commands.clear_current_lab", lambda: called.append(True))
    result = CliRunner().invoke(clear, [])
    assert result.exit_code == 0
    assert called == [True]


def test_cluster_info_uses_default_table_and_plugin(monkeypatch):
    monkeypatch.setattr(cluster_info_commands, "VIRLServer", lambda: object())
    monkeypatch.setattr(cluster_info_commands, "get_cml_client", lambda _s: _Client())
    fallback = []
    monkeypatch.setattr(cluster_info_commands, "cluster_list_table", lambda computes: fallback.append(computes))
    monkeypatch.setattr(
        cluster_info_commands,
        "ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    result = CliRunner().invoke(cluster_info_commands.info, [])
    assert result.exit_code == 0
    assert fallback and "c1" in fallback[0]

    rendered = []

    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr(cluster_info_commands, "ViewerPlugin", lambda **_kwargs: _Viewer())
    result = CliRunner().invoke(cluster_info_commands.info, [])
    assert result.exit_code == 0
    assert rendered and "computes" in rendered[0]


def test_cluster_info_handles_system_health_failure(monkeypatch):
    class _BadClient(_Client):
        def get_system_health(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(cluster_info_commands, "VIRLServer", lambda: object())
    monkeypatch.setattr(cluster_info_commands, "get_cml_client", lambda _s: _BadClient())
    result = CliRunner().invoke(cluster_info_commands.info, [])
    assert result.exit_code == 1
    assert "Failed to get system health data" in result.output


def test_group_delete_update_and_list_paths(monkeypatch):
    client = _Client()
    monkeypatch.setattr("virl.cli.groups.delete.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.groups.delete.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.groups.update.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.groups.update.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.groups.ls.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.groups.ls.commands.get_cml_client", lambda _s: client)

    out = CliRunner().invoke(delete_groups, ["group1"])
    assert out.exit_code == 0
    assert client.group_management.deleted == ["g1"]

    out = CliRunner().invoke(delete_groups, ["missing"])
    assert out.exit_code == 1
    assert "not found" in out.output

    client.group_management.delete_group = lambda _gid: (_ for _ in ()).throw(RuntimeError("delete fail"))
    out = CliRunner().invoke(delete_groups, ["group2"])
    assert out.exit_code == 1
    assert "Failed to delete group" in out.output

    out = CliRunner().invoke(update_groups, ["group1", "--member", "alice"])
    assert out.exit_code == 0
    assert client.group_management.updated

    client.group_management.update_group = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fail"))
    out = CliRunner().invoke(update_groups, ["group1"])
    assert out.exit_code == 1
    assert "Failed to update group" in out.output

    monkeypatch.setattr(
        "virl.cli.groups.ls.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    out = CliRunner().invoke(list_groups, [])
    assert out.exit_code == 0


def test_group_list_uses_plugin_visualizer(monkeypatch):
    client = _Client()
    called = []
    monkeypatch.setattr("virl.cli.groups.ls.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.groups.ls.commands.get_cml_client", lambda _s: client)

    _install_viewer(monkeypatch, "virl.cli.groups.ls.commands", called)
    out = CliRunner().invoke(list_groups, [])
    assert out.exit_code == 0
    assert called and "groups" in called[0]


def test_id_command_paths(monkeypatch):
    monkeypatch.setattr("virl.cli.id.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.id.commands.get_cml_client", lambda _s: _Client())
    monkeypatch.setattr("virl.cli.id.commands.get_current_lab", lambda: "lab1")
    monkeypatch.setattr("virl.cli.id.commands.safe_join_existing_lab", lambda _id, _c: types.SimpleNamespace(title="Lab One"))
    out = CliRunner().invoke(lid, [])
    assert out.exit_code == 0
    assert "Lab One (ID: lab1)" in out.output

    monkeypatch.setattr("virl.cli.id.commands.safe_join_existing_lab", lambda _id, _c: None)
    monkeypatch.setattr("virl.cli.id.commands.CachedLab", lambda _id, _path: types.SimpleNamespace(title="Cached Lab"))
    monkeypatch.setattr("virl.cli.id.commands.get_current_lab_link", lambda: "/tmp/current")
    out = CliRunner().invoke(lid, [])
    assert out.exit_code == 0
    assert "Cached Lab" in out.output

    monkeypatch.setattr("virl.cli.id.commands.CachedLab", lambda _id, _path: (_ for _ in ()).throw(RuntimeError("bad")))
    out = CliRunner().invoke(lid, [])
    assert out.exit_code == 0
    assert "not on server or in cache" in out.output

    monkeypatch.setattr("virl.cli.id.commands.get_current_lab", lambda: None)
    out = CliRunner().invoke(lid, [])
    assert out.exit_code == 0


def test_search_paths(monkeypatch):
    monkeypatch.setattr(
        "virl.cli.search.commands.get_repos",
        lambda org, query: [{"full_name": "o/r", "stargazers_count": 1, "description": "d"}],
    )
    monkeypatch.setattr(
        "virl.cli.search.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    called = []
    monkeypatch.setattr("virl.cli.search.commands.repo_table", lambda repos: called.append(repos))
    out = CliRunner().invoke(search, ["foo"])
    assert out.exit_code == 0
    assert "Displaying 1 Results For foo" in out.output
    assert called

    rendered = []
    _install_viewer(monkeypatch, "virl.cli.search.commands", rendered)
    out = CliRunner().invoke(search, [])
    assert out.exit_code == 0
    assert "Displaying 1 Results" in out.output
    assert rendered and "repos" in rendered[0]
