import functools
import logging
import os
import pdb
import sys
import traceback
import unittest

import requests_mock
import respx
from click.testing import CliRunner
from httpx import Response
from virl2_client import ClientLibrary

from .mocks import MockCMLServer

# set to warning to hide unwanted HTTP requests (httpx 2.10-, httpx2 2.11+)
for _http_logger in ("httpx", "httpx2"):
    logging.getLogger(_http_logger).setLevel(logging.WARNING)


def _ensure_httpcore2_mocker():
    """Register respx's httpcore2 mocker if pytest-httpx2 has not already done so.

    respx only patches httpcore by default. virl2_client 2.11+ speaks HTTP through
    httpx2/httpcore2, so the mock router must target those modules instead.
    pytest-httpx2 registers this mocker as a pytest plugin; define the same subclass
    here so the unittest suite works without that plugin installed.
    """
    from respx.mocks import HTTPCoreMocker, Mocker

    if "httpcore2" in Mocker.registry:
        return

    class HTTPCore2Mocker(HTTPCoreMocker):
        name = "httpcore2"
        targets = [
            "httpcore2._sync.connection.HTTPConnection",
            "httpcore2._sync.connection_pool.ConnectionPool",
            "httpcore2._sync.http_proxy.HTTPProxy",
            "httpcore2._async.connection.AsyncHTTPConnection",
            "httpcore2._async.connection_pool.AsyncConnectionPool",
            "httpcore2._async.http_proxy.AsyncHTTPProxy",
        ]

    # Class body registers the mocker via Mocker.__init_subclass__.
    _ = HTTPCore2Mocker


def _respx_using():
    """respx transport backend matching the installed virl2_client HTTP stack."""
    import virl2_client.models.authentication as auth

    if getattr(auth, "httpx2", None) is None:
        return "httpcore"
    _ensure_httpcore2_mocker()
    return "httpcore2"


def setup_cml_environ():
    os.environ["VIRL_HOST"] = "localhost"
    os.environ["VIRL_USERNAME"] = "admin"
    os.environ["VIRL_PASSWORD"] = "admin"
    os.environ["CML2_PLUS"] = "true"
    os.environ["CML_VERIFY_CERT"] = "false"
    os.environ["NSO_HOST"] = "localhost"
    os.environ["NSO_USERNAME"] = "admin"
    os.environ["NSO_PASSWORD"] = "admin"


def debug_on(*exceptions):
    if not exceptions:
        exceptions = (AssertionError,)

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except exceptions:
                info = sys.exc_info()
                traceback.print_exception(*info)
                pdb.post_mortem(info[2])

        return wrapper

    return decorator


CLIENT_VERSION = ClientLibrary.VERSION


class BaseCMLTest(unittest.TestCase):
    def get_context(self):
        if CLIENT_VERSION >= CLIENT_VERSION.__class__("2.5.0"):
            self.setup_func = self.uni_respx
            return respx.mock(assert_all_called=False, using=_respx_using())
        else:
            self.setup_func = self.uni_request
            return requests_mock.Mocker()

    def setUp(self):
        try:
            os.makedirs(".virl")
        except OSError:
            pass
        # Only doing this because we don't have a better way of controlling
        # injection of VIRL_HOST
        virl = self.get_virl()
        runner = CliRunner()
        with self.get_context() as m:
            self.setup_mocks(m)
            runner.invoke(virl, ["use", self.get_test_title()])

    def get_virl(self):
        # This bit of hackery is done since coverage loads all modules into the same
        # namespace.  We need to reload our virl module to get this to recognize
        # the new environment.
        try:
            del sys.modules["virl.cli.main"]
        except KeyError:
            pass

        setup_cml_environ()
        from virl.cli.main import virl

        return virl

    def get_api_path(self, path):
        return "https://localhost/api/v0/{}".format(path)

    def get_test_id(self):
        return "5f0d96"

    def get_test_title(self):
        return "Mock Test"

    def get_alt_id(self):
        return "5eaea5"

    def get_alt_title(self):
        return "Other Lab"

    def get_cml24_id(self):
        return "88119b68-9d08-40c4-90f5-6dc533fd0254"

    def get_cml24_rtr_1(self):
        return "88119b68-9d08-40c4-90f5-6dc533fd0256"

    def get_cml24_rtr_2(self):
        return "88119b68-9d08-40c4-90f5-6dc533fd0257"

    def prep_respx(self, **kwargs):
        if "body" in kwargs:
            kwargs["content"] = kwargs.pop("body")

        side_effect = None
        for k, v in kwargs.copy().items():
            if callable(v):
                side_effect = kwargs.pop(k)

        def side_effect_mod(req):
            if side_effect is not None:
                return Response(200, **{k: side_effect(req)})

        return kwargs, side_effect_mod if side_effect is not None else None

    def uni_respx(self, method, m, path, **kwargs):
        kwargs, side_effect = self.prep_respx(**kwargs)
        # respx uses lowercase bool
        path = path.replace("False", "false").replace("True", "true")
        path = self.get_api_path(path)
        m.request(method.upper(), path).mock(return_value=Response(200, **kwargs), side_effect=side_effect)

    def uni_request(self, method, m, path, **kwargs):
        path = self.get_api_path(path)
        m.request(method.upper(), path, **kwargs)

    def setup_mocks(self, m):
        json_dict = {
            "authentication": MockCMLServer.authentication,
            "labs": MockCMLServer.get_labs,
            "populate_lab_tiles": MockCMLServer.get_lab_tiles,
            "labs/{}/topology".format(self.get_test_id()): MockCMLServer.get_topology,
            "labs/{}/topology".format(self.get_alt_id()): MockCMLServer.get_alt_topology,
            "labs/{}/topology".format(self.get_cml24_id()): MockCMLServer.get_topology_24,
            "labs/{}/lab_element_state".format(self.get_test_id()): MockCMLServer.get_lab_element_state,
            "labs/{}/lab_element_state".format(self.get_cml24_id()): MockCMLServer.get_lab_element_state_24,
            "system_information": MockCMLServer.get_sys_info,
            "labs/{}/state".format(self.get_test_id()): "STARTED",
            "labs/{}/state".format(self.get_cml24_id()): "STARTED",
            "labs/{}/state".format(self.get_alt_id()): "STOPPED",
            "labs/{}/check_if_converged".format(self.get_test_id()): True,
            "labs/{}/check_if_converged".format(self.get_cml24_id()): True,
            "labs/{}/nodes/n1/check_if_converged".format(self.get_test_id()): True,
            "labs/{}/nodes/{}/check_if_converged".format(self.get_cml24_id(), self.get_cml24_rtr_1()): True,
            "users": MockCMLServer.get_users,
        }

        text_dict = {
            "labs/{}/download".format(self.get_test_id()): MockCMLServer.download_lab,
            "labs/{}/download".format(self.get_cml24_id()): MockCMLServer.download_lab_24,
            "labs/{}/download".format(self.get_alt_id()): MockCMLServer.download_alt_lab,
            "labs/{}/pyats_testbed".format(self.get_test_id()): MockCMLServer.get_pyats_testbed,
            "authok": MockCMLServer.auth_ok,
        }

        if isinstance(m, requests_mock.Mocker):
            self.setup_func = self.uni_request
        else:
            self.setup_func = self.uni_respx

        for path, value in json_dict.items():
            self.setup_func("get", m, path, json=value)

        for path, value in text_dict.items():
            self.setup_func("get", m, path, text=value)

        self.setup_func("post", m, "authenticate", text=MockCMLServer.authenticate)

    def add_debug_mock(self, m):
        m.register_uri(requests_mock.ANY, requests_mock.ANY, text=MockCMLServer.print_req)
