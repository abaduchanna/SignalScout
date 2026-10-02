from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Lead:
    business_name: str = ""
    owner_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    website: str = ""
    linkedin_company_url: str = ""
    source_type: str = ""
    source_urls: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    status: str = "ok"

    def merge(self, other: Lead) -> Lead:
        for key in (
            "business_name", "owner_name", "phone", "email", "address", "website",
            "linkedin_company_url", "source_type",
        ):
            if not getattr(self, key) and getattr(other, key):
                setattr(self, key, getattr(other, key))
        self.source_urls = sorted(set(self.source_urls + other.source_urls))
        self.evidence = sorted(set(self.evidence + other.evidence))
        if self.status == "ok" and other.status != "ok":
            self.status = other.status
        return self

    def as_csv_row(self) -> dict[str, str]:
        row = asdict(self)
        row["source_urls"] = " | ".join(self.source_urls)
        row["evidence"] = " | ".join(self.evidence)
        return row
