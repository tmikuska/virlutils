import types

from click.testing import CliRunner
from virl2_client.exceptions import NodeNotFound

from virl.api import NoPluginError
from virl.cli.console.commands import console
from virl.cli.ssh.commands import ssh
from virl.cli.telnet.commands import telnet
from virl.cli.tmux.commands import connect_tmux, tmux


class _Node:
    def __init__(self, label="n1", node_id="id1", node_def="iosv", active=True):
        self.label = label
        self.id = node_id
        self.node_definition = node_def
        self._active = active

    def is_active(self):
        return self._active


class _Lab:
    def __init__(self, lab_id="abcdef", title="LabOne", node=None, active_node=True):
        self.id = lab_id
        self.title = title
        self._node = node or _Node(active=active_node)

    def get_node_by_label(self, label):
        if label == "missing":
            raise NodeNotFound()
        return self._node

    def nodes(self):
        return [self._node]


def test_ssh_and_telnet_error_and_success_paths(monkeypatch):
    def _exercise_connect_cmd(module_prefix, command_obj, custom_cmd_key, custom_cmd_value, node_ip):
        server = types.SimpleNamespace(config={}, host="h", user="u")
        lab = _Lab()
        monkeypatch.setattr(f"{module_prefix}.VIRLServer", lambda: server)
        monkeypatch.setattr(f"{module_prefix}.get_cml_client", lambda _s: object())
        monkeypatch.setattr(f"{module_prefix}.get_current_lab", lambda: "lab1")
        monkeypatch.setattr(f"{module_prefix}.safe_join_existing_lab", lambda _id, _c: lab)
        monkeypatch.setattr(f"{module_prefix}.get_node_mgmt_ip", lambda _n: node_ip)
        monkeypatch.setattr(f"{module_prefix}.call", lambda _cmd: 0)

        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 0
        server.config[custom_cmd_key] = custom_cmd_value
        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 0

        server.config = {}
        monkeypatch.setattr(f"{module_prefix}.get_node_mgmt_ip", lambda _n: None)
        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 0
        lab._node._active = False
        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 0

        lab._node._active = True
        monkeypatch.setattr(f"{module_prefix}.get_node_mgmt_ip", lambda _n: node_ip)
        assert CliRunner().invoke(command_obj, ["missing"]).exit_code == 1
        monkeypatch.setattr(f"{module_prefix}.safe_join_existing_lab", lambda _id, _c: None)
        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 1
        monkeypatch.setattr(f"{module_prefix}.get_current_lab", lambda: None)
        assert CliRunner().invoke(command_obj, ["n1"]).exit_code == 1

    for args in [
        ("virl.cli.ssh.commands", ssh, "VIRL_SSH_COMMAND", "ssh {username}@{host}", "10.0.0.1"),
        ("virl.cli.telnet.commands", telnet, "VIRL_TELNET_COMMAND", "telnet {host}", "10.0.0.2"),
    ]:
        _exercise_connect_cmd(*args)


def test_console_paths(monkeypatch):
    server = types.SimpleNamespace(config={}, host="h", user="u")
    lab = _Lab(lab_id="abcdef", title="LabOne")
    monkeypatch.setattr("virl.cli.console.commands.VIRLServer", lambda: server)
    monkeypatch.setattr("virl.cli.console.commands.get_cml_client", lambda _s: object())
    monkeypatch.setattr("virl.cli.console.commands.get_current_lab", lambda: "lab1")
    monkeypatch.setattr("virl.cli.console.commands.safe_join_existing_lab", lambda _id, _c: lab)
    table_calls = []
    monkeypatch.setattr("virl.cli.console.commands.console_table", lambda consoles: table_calls.append(consoles))
    monkeypatch.setattr(
        "virl.cli.console.commands.ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(console, ["n1", "--display"]).exit_code == 0
    assert table_calls

    rendered = []

    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr("virl.cli.console.commands.ViewerPlugin", lambda **_kwargs: _Viewer())
    assert CliRunner().invoke(console, ["n1", "--display"]).exit_code == 0
    assert rendered

    monkeypatch.setattr("virl.cli.console.commands.call", lambda _cmd: 0)
    assert CliRunner().invoke(console, ["n1", "--none"]).exit_code == 0
    server.config["CML_CONSOLE_COMMAND"] = "ssh {user}@{host} {console}"
    assert CliRunner().invoke(console, ["n1", "--none"]).exit_code == 0
    server.config = {}
    monkeypatch.setattr("virl.cli.console.commands.platform.system", lambda: "Windows")

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("virl.cli.console.commands.helpers.disable_file_system_redirection", _Ctx)
    assert CliRunner().invoke(console, ["n1", "--none"]).exit_code == 0

    lab._node._active = False
    assert CliRunner().invoke(console, ["n1"]).exit_code == 1
    lab._node._active = True
    lab._node.node_definition = "external_connector"
    assert CliRunner().invoke(console, ["n1"]).exit_code == 0
    lab._node.node_definition = "iosv"
    assert CliRunner().invoke(console, ["missing"]).exit_code == 1
    monkeypatch.setattr("virl.cli.console.commands.safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(console, ["n1"]).exit_code == 1
    monkeypatch.setattr("virl.cli.console.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(console, ["n1"]).exit_code == 1


def test_connect_tmux_and_tmux_command(monkeypatch):
    sent = []

    class _Pane:
        def send_keys(self, cmd, suppress_history=True):
            sent.append(cmd)

    class _Window:
        def __init__(self):
            self.panes = [_Pane()]

        def split(self):
            p = _Pane()
            self.panes.append(p)
            return p

        def select_layout(self, _layout):
            return None

        def cmd(self, *_args):
            return None

    class _Session:
        def __init__(self):
            self.windows = [_Window()]

        def new_window(self, window_name):
            w = _Window()
            self.windows.append(w)
            return w

        def switch_client(self):
            sent.append("switch")

        def attach(self):
            sent.append("attach")

    class _Server:
        def new_session(self, session_name, kill_session=True):
            return _Session()

    monkeypatch.setattr("virl.cli.tmux.commands.libtmux.server.Server", lambda: _Server())
    monkeypatch.delenv("TMUX", raising=False)
    node_cmds = [(_Node(label="n1"), "cmd1"), (_Node(label="n2"), "cmd2")]
    connect_tmux("s1", node_cmds, "panes")
    connect_tmux("s2", node_cmds, "windows")
    assert "attach" in sent
    monkeypatch.setenv("TMUX", "1")
    connect_tmux("s3", node_cmds, "panes")
    assert "switch" in sent

    server = types.SimpleNamespace(config={}, host="h", user="u")
    lab = types.SimpleNamespace(id="abcdef", title="Lab:One", nodes=lambda: [_Node(label="n1", node_def="iosv", active=True)])
    monkeypatch.setattr("virl.cli.tmux.commands.VIRLServer", lambda: server)
    monkeypatch.setattr("virl.cli.tmux.commands.get_cml_client", lambda _s: object())
    monkeypatch.setattr("virl.cli.tmux.commands.get_current_lab", lambda: "lab1")
    monkeypatch.setattr("virl.cli.tmux.commands.safe_join_existing_lab", lambda _id, _c: lab)
    called = []
    monkeypatch.setattr(
        "virl.cli.tmux.commands.connect_tmux",
        lambda title, node_console_cmd, group: called.append((title, group, node_console_cmd)),
    )
    assert CliRunner().invoke(tmux, ["--group", "panes"]).exit_code == 0
    assert called
    server.config["CML_CONSOLE_COMMAND"] = "ssh {user}@{host} {console}"
    assert CliRunner().invoke(tmux, ["--group", "windows"]).exit_code == 0

    # No valid nodes
    bad_lab = types.SimpleNamespace(
        id="abcdef",
        title="LabOne",
        nodes=lambda: [_Node(label="e1", node_def="external_connector", active=True), _Node(label="n2", node_def="iosv", active=False)],
    )
    monkeypatch.setattr("virl.cli.tmux.commands.safe_join_existing_lab", lambda _id, _c: bad_lab)
    assert CliRunner().invoke(tmux, []).exit_code == 1
    monkeypatch.setattr("virl.cli.tmux.commands.safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(tmux, []).exit_code == 1
    monkeypatch.setattr("virl.cli.tmux.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(tmux, []).exit_code == 1
