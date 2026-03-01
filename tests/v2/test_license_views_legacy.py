from virl.cli.views.license.license_views import (
    license_features_table,
    print_authorization,
    print_features,
    print_registration,
)


def test_license_view_status_branches_and_fallback(monkeypatch):
    calls = []

    def fake_tabulate(_table, _headers, tablefmt):
        calls.append(tablefmt)
        if tablefmt == "fancy_grid":
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "boom")
        return "grid-output"

    monkeypatch.setattr("virl.cli.views.license.license_views.tabulate.tabulate", fake_tabulate)
    monkeypatch.setattr("virl.cli.views.license.license_views.click.echo", lambda _msg: None)

    license_features_table([{"id": "f1", "name": "Feature1", "in_use": True}])

    print_registration(
        {
            "status": "IN_PROGRESS",
            "expires": "never",
            "smart_account": "sa",
            "virtual_account": "va",
            "register_time": {"attempted": "now", "success": "FAILED"},
            "renew_time": {"scheduled": None},
        }
    )
    print_registration(
        {
            "status": "UNKNOWN",
            "expires": "never",
            "smart_account": "sa",
            "virtual_account": "va",
            "register_time": {"attempted": None, "success": "SUCCESS"},
            "renew_time": {"scheduled": "later"},
        }
    )

    print_authorization(
        {
            "status": "OUT_OF_COMPLIANCE",
            "expires": "never",
            "renew_time": {"attempted": "now", "status": "FAILED", "scheduled": None},
        }
    )
    print_authorization(
        {
            "status": "IN_COMPLIANCE",
            "expires": "never",
            "renew_time": {"attempted": "now", "status": "NOT STARTED", "scheduled": "soon"},
        }
    )
    print_authorization(
        {
            "status": "IN_COMPLIANCE",
            "expires": "never",
            "renew_time": {"attempted": None, "status": "SUCCEEDED", "scheduled": "soon"},
        }
    )

    print_features(
        [
            {"name": "f1", "description": "d", "in_use": True, "status": "IN_COMPLIANCE", "version": "1"},
            {"name": "f2", "description": "d", "in_use": False, "status": "ERROR", "version": "2"},
            {"name": "f3", "description": "d", "in_use": False, "status": "INIT", "version": "3"},
        ]
    )

    assert "fancy_grid" in calls and "grid" in calls
