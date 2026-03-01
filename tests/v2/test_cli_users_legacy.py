from click.testing import CliRunner
import pytest

from virl.api import NoPluginError
from virl.cli.users.create.commands import confirm_password, create_users
from virl.cli.users.ls.commands import list_users
from virl.cli.users.update.commands import get_password_dict, update_users


def _install_user_viewer(monkeypatch, rendered):
    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr("virl.cli.users.ls.commands.ViewerPlugin", lambda **_kwargs: _Viewer())


class _GroupMgmt:
    def group_id(self, group_name):
        return {"group1": "g1", "group2": "g2"}[group_name]

    def groups(self):
        return [{"id": "g1", "name": "group1"}, {"id": "g2", "name": "group2"}]


class _UserMgmt:
    def __init__(self):
        self.created = []
        self.updated = []

    def create_user(self, **kwargs):
        if kwargs["username"] == "bad":
            raise RuntimeError("create fail")
        self.created.append(kwargs)

    def update_user(self, **kwargs):
        if kwargs.get("user_id") == "u_bad":
            raise RuntimeError("update fail")
        self.updated.append(kwargs)

    def users(self):
        return [
            {"id": "u1", "username": "alice", "groups": ["g1"], "labs": ["l1"]},
            {"id": "u_bad", "username": "bad", "groups": ["g2"], "labs": ["l2"]},
        ]


class _Client:
    def __init__(self):
        self.group_management = _GroupMgmt()
        self.user_management = _UserMgmt()

    def all_labs(self, show_all=True):
        return [type("Lab", (), {"id": "l1", "title": "Lab One"})(), type("Lab", (), {"id": "l2", "title": "Lab Two"})()]


def test_create_users_and_confirm_password_paths(monkeypatch):
    client = _Client()
    monkeypatch.setattr("virl.cli.users.create.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.users.create.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.users.create.commands.confirm_password", lambda _u: "pw")

    out = CliRunner().invoke(create_users, ["alice", "--group", "group1", "--admin"])
    assert out.exit_code == 0
    assert client.user_management.created[0]["groups"] == ["g1"]
    assert client.user_management.created[0]["admin"] is True

    out = CliRunner().invoke(create_users, ["bad"])
    assert out.exit_code == 1
    assert "Failed to create user" in out.output

    monkeypatch.setattr(
        "virl.cli.users.create.commands.getpass.getpass",
        lambda prompt: "p2" if "Re-Enter" in prompt else "p1",
    )
    with pytest.raises(SystemExit):
        confirm_password("alice")

    monkeypatch.setattr(
        "virl.cli.users.create.commands.getpass.getpass",
        lambda _prompt: "same",
    )
    assert confirm_password("alice") == "same"


def test_get_password_dict(monkeypatch):
    monkeypatch.setattr(
        "virl.cli.users.update.commands.getpass.getpass",
        lambda prompt: "old" if "old password" in prompt else "new",
    )
    assert get_password_dict("alice") == {"old_password": "old", "new_password": "new"}


def test_update_users_paths(monkeypatch):
    client = _Client()
    monkeypatch.setattr("virl.cli.users.update.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.users.update.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.users.update.commands.get_password_dict", lambda _u: {"old_password": "o", "new_password": "n"})

    out = CliRunner().invoke(update_users, ["alice", "--group", "group1", "--change-password"])
    assert out.exit_code == 0
    assert client.user_management.updated
    assert client.user_management.updated[0]["groups"] == ["g1"]
    assert "password_dict" in client.user_management.updated[0]

    out = CliRunner().invoke(update_users, ["alice", "--remove-from-all-groups"])
    assert out.exit_code == 0
    assert client.user_management.updated[-1]["groups"] == []

    out = CliRunner().invoke(update_users, ["placeholder", "--all-users"])
    assert out.exit_code == 1
    assert "Failed to create user" in out.output


def test_list_users_plugin_and_fallback(monkeypatch):
    client = _Client()
    monkeypatch.setattr("virl.cli.users.ls.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.users.ls.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.users.ls.commands.user_list_table", lambda _users, verbose=False: None)
    monkeypatch.setattr(
        "virl.cli.users.ls.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(list_users, []).exit_code == 0

    rendered = []
    _install_user_viewer(monkeypatch, rendered)
    assert CliRunner().invoke(list_users, ["--verbose"]).exit_code == 0
    assert rendered and "users" in rendered[0]
