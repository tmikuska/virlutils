import types

import pytest
from click.testing import CliRunner

from virl.api import NoPluginError
from virl.cli.command.commands import command as command_cmd
from virl.cli.license.deregister.commands import deregister
from virl.cli.license.features.show.commands import show as features_show
from virl.cli.license.features.update.commands import update as features_update
from virl.cli.license.register.commands import register
from virl.cli.license.renew.authorization.commands import authorization
from virl.cli.license.renew.registration.commands import registration
from virl.cli.license.show.commands import show as license_show
from virl.cli.version.commands import version

LP_REGISTER = "virl.cli.license.register.commands"
LP_DEREGISTER = "virl.cli.license.deregister.commands"
LP_FEATURES_SHOW = "virl.cli.license.features.show.commands"
LP_FEATURES_UPDATE = "virl.cli.license.features.update.commands"
LP_LICENSE_SHOW = "virl.cli.license.show.commands"
LP_RENEW_AUTH = "virl.cli.license.renew.authorization.commands"
LP_RENEW_REG = "virl.cli.license.renew.registration.commands"


class FakeServer:
    host = "cml.example.local"
    user = "admin"
    passwd = "password"
    config = {}


class FakeLicensing:
    def __init__(self):
        self.calls = []

    def status(self):
        self.calls.append(("status",))
        return {"transport": {"default_ssms": "https://ssms.example.local"}}

    def set_transport(self, ssms, proxy, port):
        self.calls.append(("set_transport", ssms, proxy, port))

    def delete_certificate(self):
        self.calls.append(("delete_certificate",))

    def set_default_transport(self):
        self.calls.append(("set_default_transport",))

    def upload_certificate(self, contents):
        self.calls.append(("upload_certificate", contents))

    def register(self, token, reregister):
        self.calls.append(("register", token, reregister))

    def deregister(self):
        self.calls.append(("deregister",))

    def features(self):
        self.calls.append(("features",))
        return [{"id": "f1", "name": "feature", "in_use": 1}]

    def update_features(self, payload):
        self.calls.append(("update_features", payload))

    def renew_authorization(self):
        self.calls.append(("renew_authorization",))

    def register_renew(self):
        self.calls.append(("register_renew",))


def _patch_server_and_client(monkeypatch, module_path, licensing):
    monkeypatch.setattr(f"{module_path}.VIRLServer", lambda: FakeServer())
    monkeypatch.setattr(
        f"{module_path}.get_cml_client",
        lambda _server: types.SimpleNamespace(licensing=licensing, system_info=lambda: {"version": "2.8.0"}),
    )


def test_version_command_paths(monkeypatch):
    monkeypatch.setattr("virl.cli.version.commands.VIRLServer", lambda: FakeServer())
    monkeypatch.setattr(
        "virl.cli.version.commands.get_cml_client",
        lambda _server: types.SimpleNamespace(system_info=lambda: {"version": "2.9.1"}),
    )
    ok = CliRunner().invoke(version, [])
    assert ok.exit_code == 0
    assert "cmlutils Version:" in ok.output
    assert "CML Controller Version: 2.9.1" in ok.output

    monkeypatch.setattr(
        "virl.cli.version.commands.get_cml_client",
        lambda _server: types.SimpleNamespace(system_info=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    unknown = CliRunner().invoke(version, [])
    assert unknown.exit_code == 0
    assert "CML Controller Version: Unknown" in unknown.output


class _FakeCred:
    def __init__(self):
        self.username = None
        self.password = None


class _FakeDevice:
    def __init__(self, name):
        self.name = name
        self.credentials = types.SimpleNamespace(default=_FakeCred(), enable=types.SimpleNamespace(password=None))


class _FakePyats:
    def __init__(self, _lab):
        self._testbed = types.SimpleNamespace(
            devices={
                "terminal_server": _FakeDevice("terminal_server"),
                "rtr-1": _FakeDevice("rtr-1"),
            }
        )

    def sync_testbed(self, _user, _passwd):
        return None

    def run_command(self, node, command):
        return f"ran {command} on {node}"

    def run_config_command(self, node, command):
        return f"configured {command} on {node}"


def _patch_command_env(monkeypatch, pyats_cls=_FakePyats, current_lab="lab-1", lab_obj=object()):
    monkeypatch.setattr("virl.cli.command.commands.VIRLServer", lambda: FakeServer())
    monkeypatch.setattr("virl.cli.command.commands.get_cml_client", lambda _server: object())
    monkeypatch.setattr("virl.cli.command.commands.get_current_lab", lambda: current_lab)
    monkeypatch.setattr("virl.cli.command.commands.safe_join_existing_lab", lambda _lab_id, _client: lab_obj)
    monkeypatch.setattr("virl.cli.command.commands.ClPyats", pyats_cls)


@pytest.mark.parametrize(
    "args,expected",
    [
        (["rtr-1", "show version"], "ran show version on rtr-1"),
        (["rtr-1", "hostname r1", "--config"], "configured hostname r1 on rtr-1"),
    ],
)
def test_command_executes_pyats_paths(monkeypatch, args, expected):
    _patch_command_env(monkeypatch)
    result = CliRunner().invoke(command_cmd, args)
    assert result.exit_code == 0
    assert expected in result.output


def test_command_errors_when_no_current_lab(monkeypatch):
    _patch_command_env(monkeypatch, current_lab=None)
    result = CliRunner().invoke(command_cmd, ["rtr-1", "show version"])
    assert result.exit_code == 1
    assert "No current lab set" in result.output


def test_command_errors_when_current_lab_lookup_fails(monkeypatch):
    _patch_command_env(monkeypatch, lab_obj=None)
    result = CliRunner().invoke(command_cmd, ["rtr-1", "show version"])
    assert result.exit_code == 1
    assert "Unable to find lab lab-1" in result.output


def test_command_errors_when_pyats_missing(monkeypatch):
    from virl.cli.command.commands import PyatsNotInstalled

    class _MissingPyats:
        def __init__(self, _lab):
            raise PyatsNotInstalled()

    _patch_command_env(monkeypatch, pyats_cls=_MissingPyats)
    result = CliRunner().invoke(command_cmd, ["rtr-1", "show version"])
    assert result.exit_code == 1
    assert "pyATS is not installed" in result.output


def test_command_handles_unsupported_device(monkeypatch):
    from virl.cli.command.commands import PyatsDeviceNotFound

    class _DeviceMissingPyats(_FakePyats):
        def run_command(self, _node, _command):
            raise PyatsDeviceNotFound()

    _patch_command_env(monkeypatch, pyats_cls=_DeviceMissingPyats)
    result = CliRunner().invoke(command_cmd, ["rtr-1", "show version"])
    assert result.exit_code == 0
    assert "not supported by pyATS" in result.output


def test_command_handles_runtime_failure(monkeypatch):
    class _ErrorPyats(_FakePyats):
        def run_command(self, _node, _command):
            raise RuntimeError("failed")

    _patch_command_env(monkeypatch, pyats_cls=_ErrorPyats)
    result = CliRunner().invoke(command_cmd, ["rtr-1", "show version"])
    assert result.exit_code == 1
    assert "Failed to run 'show version' on 'rtr-1'" in result.output


def test_license_register_success_and_default_paths(monkeypatch, tmp_path):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    cert = tmp_path / "license.pem"
    cert.write_text("CERTDATA")

    ok = CliRunner().invoke(
        register,
        [
            "--token",
            "abc123",
            "--smart-license-server",
            "https://sat.example",
            "--proxy-host",
            "proxy.local",
            "--proxy-port",
            "8080",
            "--certificate",
            str(cert),
        ],
    )
    assert ok.exit_code == 0
    assert ("set_transport", "https://sat.example", "proxy.local", 8080) in licensing.calls
    assert ("upload_certificate", "CERTDATA") in licensing.calls
    assert ("register", "abc123", False) in licensing.calls

    defaults = CliRunner().invoke(register, ["--token", "abc123"])
    assert defaults.exit_code == 0
    assert ("delete_certificate",) in licensing.calls
    assert ("set_default_transport",) in licensing.calls


@pytest.mark.parametrize(
    "args,expected_call",
    [
        (["--token", "abc123", "--proxy-host", "proxy.local"], ("set_transport", "https://ssms.example.local", "proxy.local", 80)),
        (["--token", "abc123", "--smart-license-server", "https://sat.example"], ("set_transport", "https://sat.example", None, None)),
    ],
)
def test_license_register_transport_variants(monkeypatch, args, expected_call):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    result = CliRunner().invoke(register, args)
    assert result.exit_code == 0
    assert expected_call in licensing.calls


def test_license_register_rejects_missing_certificate_file(monkeypatch):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    result = CliRunner().invoke(register, ["--token", "abc123", "--certificate", "/missing/cert.pem"])
    assert result.exit_code == 1
    assert "is not a valid file" in result.output


@pytest.mark.parametrize(
    "attr_name,args,expected_error",
    [
        ("set_transport", ["--token", "abc123", "--proxy-host", "proxy.local"], "Failed to configure Smart License server and proxy"),
        ("register", ["--token", "abc123"], "Failed to register with Smart Licensing"),
    ],
)
def test_license_register_handles_failures(monkeypatch, attr_name, args, expected_error):
    licensing = FakeLicensing()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("fail")

    setattr(licensing, attr_name, _boom)
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    result = CliRunner().invoke(register, args)
    assert result.exit_code == 1
    assert expected_error in result.output


def test_license_register_handles_certificate_upload_failure(monkeypatch, tmp_path):
    licensing = FakeLicensing()
    cert = tmp_path / "license.pem"
    cert.write_text("CERTDATA")

    def _boom(_contents):
        raise RuntimeError("upload fail")

    licensing.upload_certificate = _boom
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    result = CliRunner().invoke(register, ["--token", "abc123", "--certificate", str(cert)])
    assert result.exit_code == 1
    assert "Failed to upload certificate" in result.output


def test_license_register_ignores_delete_certificate_failure(monkeypatch):
    licensing = FakeLicensing()

    def _boom():
        raise RuntimeError("delete fail")

    licensing.delete_certificate = _boom
    _patch_server_and_client(monkeypatch, LP_REGISTER, licensing)
    result = CliRunner().invoke(register, ["--token", "abc123"])
    assert result.exit_code == 0
    assert ("set_default_transport",) in licensing.calls


@pytest.mark.parametrize(
    "confirm_value,args,expect_call,expect_text",
    [
        ("n", [], False, "Not deregistering"),
        ("y", [], True, None),
        (None, ["--no-confirm"], True, None),
    ],
)
def test_license_deregister_paths(monkeypatch, confirm_value, args, expect_call, expect_text):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, LP_DEREGISTER, licensing)
    if confirm_value is not None:
        monkeypatch.setattr("builtins.input", lambda _prompt: confirm_value)
    result = CliRunner().invoke(deregister, args)
    assert result.exit_code == 0
    assert (("deregister",) in licensing.calls) is expect_call
    if expect_text:
        assert expect_text in result.output


def test_license_deregister_handles_api_failure(monkeypatch):
    licensing = FakeLicensing()

    def _boom():
        raise RuntimeError("deregister fail")

    licensing.deregister = _boom
    _patch_server_and_client(monkeypatch, LP_DEREGISTER, licensing)
    result = CliRunner().invoke(deregister, ["--no-confirm"])
    assert result.exit_code == 1
    assert "Failed to deregister with Smart Licensing" in result.output


@pytest.mark.parametrize(
    "module_path,command_obj,viewer_attr,table_attr,kw,arg_name",
    [
        (LP_FEATURES_SHOW, features_show, "ViewerPlugin", "license_features_table", "features", "features"),
        (LP_LICENSE_SHOW, license_show, "ViewerPlugin", "license_details_table", "license", "license"),
    ],
)
def test_license_show_commands_use_fallback_and_plugin(monkeypatch, module_path, command_obj, viewer_attr, table_attr, kw, arg_name):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, module_path, licensing)

    fallback_calls = []
    monkeypatch.setattr(
        f"{module_path}.{viewer_attr}",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    monkeypatch.setattr(f"{module_path}.{table_attr}", lambda payload: fallback_calls.append(payload))
    fallback = CliRunner().invoke(command_obj, [])
    assert fallback.exit_code == 0
    assert fallback_calls

    rendered = []

    class _Viewer:
        def visualize(self, **kwargs):
            rendered.append(kwargs)

    monkeypatch.setattr(f"{module_path}.{viewer_attr}", lambda **_kwargs: _Viewer())
    plugin = CliRunner().invoke(command_obj, [])
    assert plugin.exit_code == 0
    assert rendered and arg_name in rendered[0]


@pytest.mark.parametrize(
    "module_path,command_obj,attr_to_boom,expected_text",
    [
        (LP_FEATURES_SHOW, features_show, "features", "Failed to get license features"),
        (LP_LICENSE_SHOW, license_show, "status", "Failed to get license details"),
    ],
)
def test_license_show_commands_handle_api_failures(monkeypatch, module_path, command_obj, attr_to_boom, expected_text):
    licensing = FakeLicensing()

    def _boom():
        raise RuntimeError("fail")

    setattr(licensing, attr_to_boom, _boom)
    _patch_server_and_client(monkeypatch, module_path, licensing)
    result = CliRunner().invoke(command_obj, [])
    assert result.exit_code == 1
    assert expected_text in result.output


def test_license_update_and_renew_success_paths(monkeypatch):
    licensing = FakeLicensing()
    _patch_server_and_client(monkeypatch, LP_FEATURES_UPDATE, licensing)
    _patch_server_and_client(monkeypatch, LP_RENEW_AUTH, licensing)
    _patch_server_and_client(monkeypatch, LP_RENEW_REG, licensing)

    assert CliRunner().invoke(features_update, ["--id", "f1", "--value", "5"]).exit_code == 0
    assert CliRunner().invoke(authorization, []).exit_code == 0
    assert CliRunner().invoke(registration, []).exit_code == 0
    assert ("update_features", {"f1": 5}) in licensing.calls
    assert ("renew_authorization",) in licensing.calls
    assert ("register_renew",) in licensing.calls


@pytest.mark.parametrize(
    "module_path,command_obj,attr_name,args,expected_text",
    [
        (LP_FEATURES_UPDATE, features_update, "update_features", ["--id", "f1", "--value", "5"], "Failed to update features"),
        (LP_RENEW_AUTH, authorization, "renew_authorization", [], "Failed to renew authorization"),
        (LP_RENEW_REG, registration, "register_renew", [], "Failed to renew registration"),
    ],
)
def test_license_update_and_renew_error_paths(monkeypatch, module_path, command_obj, attr_name, args, expected_text):
    licensing = FakeLicensing()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("fail")

    setattr(licensing, attr_name, _boom)
    _patch_server_and_client(monkeypatch, module_path, licensing)
    result = CliRunner().invoke(command_obj, args)
    assert result.exit_code == 1
    assert expected_text in result.output
