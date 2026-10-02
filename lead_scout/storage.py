from __future__ import annotations

import csv
from pathlib import Path

from .extract import normalized_domain
from .models import Lead

FIELDS = (
    "business_name", "owner_name", "phone", "email", "address", "website",
    "linkedin_company_url", "source_type", "source_urls", "evidence", "status",
)


def read_seeds(path: str | Path) -> list[Lead]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return [Lead(**{key: value for key, value in row.items() if key in Lead.__dataclass_fields__})
                for row in csv.DictReader(handle)]


def dedupe(leads: list[Lead]) -> list[Lead]:
    merged: dict[str, Lead] = {}
    for lead in leads:
        domain = normalized_domain(lead.website) if lead.website else ""
        key = domain or f"{lead.business_name.lower()}|{lead.address.lower()}"
        if not key.strip("|"):
            key = f"unknown-{len(merged)}"
        merged.setdefault(key, Lead()).merge(lead)
    return list(merged.values())


def write_csv(path: str | Path, leads: list[Lead]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.as_csv_row())
