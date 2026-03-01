from virl.cli.views.images.image_views import image_list_table
from virl.cli.views.license.license_views import (
    license_details_table,
    license_features_table,
    print_authorization,
    print_features,
    print_registration,
)


def _sample_license_payload():
    return {
        "registration": {
            "status": "COMPLETED",
            "expires": "2099-01-01",
            "smart_account": "Acct",
            "virtual_account": "VA",
            "register_time": {"attempted": "2025-01-01", "success": "SUCCESS"},
            "renew_time": {"scheduled": "2025-02-01"},
        },
        "authorization": {
            "status": "IN_COMPLIANCE",
            "expires": "2099-01-01",
            "renew_time": {"attempted": "2025-01-01", "status": "SUCCEEDED", "scheduled": "2025-02-01"},
        },
        "features": [
            {
                "name": "feature-1",
                "description": "desc",
                "in_use": 1,
                "status": "IN_COMPLIANCE",
                "version": "1.0",
            },
            {
                "name": "feature-2",
                "description": "desc",
                "in_use": 0,
                "status": "NON_COMPLIANT",
                "version": "1.0",
            },
            {
                "name": "feature-3",
                "description": "desc",
                "in_use": 0,
                "status": "INIT",
                "version": "1.0",
            },
        ],
    }


def test_license_details_table_renders_all_sections(monkeypatch):
    payload = _sample_license_payload()
    echoed = []
    monkeypatch.setattr("virl.cli.views.license.license_views.click.secho", lambda msg: echoed.append(msg))
    monkeypatch.setattr("virl.cli.views.license.license_views.click.echo", lambda msg: echoed.append(msg))

    license_details_table(payload)

    assert "Registration Details" in echoed
    assert "Authorization Details" in echoed
    assert "Features" in echoed


def test_license_print_helpers_handle_na_and_status_colors(monkeypatch):
    echoed = []
    monkeypatch.setattr("virl.cli.views.license.license_views.click.echo", lambda msg: echoed.append(msg))

    reg = {
        "status": "FAILED",
        "expires": "never",
        "smart_account": "acct",
        "virtual_account": "va",
        "register_time": {"attempted": None, "success": "FAILED"},
        "renew_time": {"scheduled": None},
    }
    auth = {
        "status": "OUT_OF_COMPLIANCE",
        "expires": "never",
        "renew_time": {"attempted": "now", "status": "NOT STARTED", "scheduled": None},
    }
    features = [
        {"name": "f", "description": "d", "in_use": 0, "status": "INIT", "version": "1"},
        {"name": "f2", "description": "d2", "in_use": 1, "status": "BROKEN", "version": "2"},
    ]

    print_registration(reg)
    print_authorization(auth)
    print_features(features)

    assert len(echoed) == 3


def test_license_and_image_tables_fallback_to_grid_on_unicode_error(monkeypatch):
    calls = []

    def fake_tabulate(_table, _headers, tablefmt):
        calls.append(tablefmt)
        if tablefmt == "fancy_grid":
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "boom")
        return "grid-output"

    monkeypatch.setattr("virl.cli.views.license.license_views.tabulate.tabulate", fake_tabulate)
    monkeypatch.setattr("virl.cli.views.images.image_views.tabulate.tabulate", fake_tabulate)
    monkeypatch.setattr("virl.cli.views.license.license_views.click.echo", lambda _msg: None)
    monkeypatch.setattr("virl.cli.views.images.image_views.click.echo", lambda _msg: None)

    license_features_table([{"id": "f1", "name": "feature", "in_use": 1}])
    image_list_table(
        [
            {
                "id": "img-1",
                "node_definition_id": "def-1",
                "label": "image",
                "description": "desc",
                "ram": 1024,
                "cpus": 1,
                "boot_disk_size": 16,
            }
        ]
    )

    assert calls.count("fancy_grid") >= 2
    assert calls.count("grid") >= 2
