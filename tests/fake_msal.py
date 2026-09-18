from __future__ import annotations


class FakeMsalApp:
    """Stands in for msal.PublicClientApplication."""

    def __init__(self, accounts=None, silent=None, interactive=None, device=None, raise_interactive=False):
        self.accounts = accounts or []
        self.silent, self.interactive, self.device = silent, interactive, device
        self.raise_interactive = raise_interactive
        self.calls: list[str] = []

    def get_accounts(self):
        return self.accounts

    def remove_account(self, account):
        self.accounts = [a for a in self.accounts if a is not account]

    def acquire_token_silent(self, scopes, account=None):
        self.calls.append("silent")
        return self.silent

    def acquire_token_interactive(self, scopes, prompt=None, timeout=None):
        self.calls.append("interactive")
        if self.raise_interactive:
            raise RuntimeError("no browser")
        return self.interactive

    def initiate_device_flow(self, scopes):
        self.calls.append("device_start")
        return {"user_code": "ABCD-EFGH", "device_code": "dc", "verification_uri": "https://microsoft.com/devicelogin",
                "message": "To sign in, open https://microsoft.com/devicelogin and enter ABCD-EFGH"}

    def acquire_token_by_device_flow(self, flow):
        self.calls.append("device_complete")
        return self.device
