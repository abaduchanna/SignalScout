from __future__ import annotations

import requests

from ..models import Lead

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.googleMapsUri,places.businessStatus,nextPageToken"
)


def search_places(query: str, api_key: str, max_pages: int = 1) -> list[Lead]:
    if not api_key:
        raise ValueError("Google Places API key is required")
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    leads: list[Lead] = []
    token = ""
    for _ in range(max(1, min(max_pages, 3))):
        body = {"textQuery": query, "pageSize": 20, "languageCode": "en", "regionCode": "US"}
        if token:
            body["pageToken"] = token
        response = requests.post(ENDPOINT, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for place in payload.get("places", []):
            name = place.get("displayName", {}).get("text", "")
            phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber", "")
            evidence = [place.get("googleMapsUri", "")]
            business_status = place.get("businessStatus", "")
            leads.append(
                Lead(
                    business_name=name,
                    phone=phone,
                    address=place.get("formattedAddress", ""),
                    website=place.get("websiteUri", ""),
                    source_type="google_places_api",
                    source_urls=[url for url in evidence if url],
                    evidence=[f"Google Place ID: {place.get('id', '')}"],
                    status="ok" if business_status in {"", "OPERATIONAL"} else business_status.lower(),
                )
            )
        token = payload.get("nextPageToken", "")
        if not token:
            break
    return leads
