import tomllib

from rca_core.tomlwrite import dumps


def test_round_trip():
    data = {"ado": {"org_url": "https://dev.azure.com/acme", "project": "Acme"},
            "git": {"current_pi": "Acme\\PI-14", "legacy_cutoff": "9.6"},
            "fields": {"summary": "Custom.RCASummary"}, "auth": {"mode": "browser"}}
    assert tomllib.loads(dumps(data)) == data
