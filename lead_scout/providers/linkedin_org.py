from __future__ import annotations

import requests


def lookup_organization(
    *, token: str, version: str, vanity_name: str = "", email_domain: str = ""
) -> dict:
    """Use LinkedIn's official Organization Lookup API; never scrape linkedin.com."""
    if not token:
        raise ValueError("LinkedIn access token is required")
    if bool(vanity_name) == bool(email_domain):
        raise ValueError("Provide exactly one of vanity_name or email_domain")
    if vanity_name:
        params = {"q": "vanityName", "vanityName": vanity_name}
    else:
        params = {"q": "emailDomain", "emailDomain": email_domain}
    response = requests.get(
        "https://api.linkedin.com/rest/organizationsLookup",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Linkedin-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
