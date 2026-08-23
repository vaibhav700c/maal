"""Shared data models for the enrichment pipeline."""
from pydantic import BaseModel, Field


class MfrInfo(BaseModel):
    name: str = ""
    code: str | None = None


class CleanRow(BaseModel):
    mfg_part_num: str
    part_desc: str
    e1_brand: str | None = None
    unilog_brand: str | None = None
    dib_brand: str | None = None
    mfr_name: str | None = None
    mfr_code: str | None = None


class Evidence(BaseModel):
    quote: str
    url: str | None = None
    tier: float = 0.0  # 0 input-only, 0.9 mfr-hosted PDF, 1.0 mfr site page


class Attribute(BaseModel):
    label: str
    value: str
    uom: str | None = None
    evidence: Evidence | None = None
    verdict: str = "UNVERIFIED"  # CONFIRMED|REFUTED|UNSUPPORTED|UNVERIFIED
    confidence: float = 0.0
    review_reason: str | None = None


class Classification(BaseModel):
    dept: str
    klass: str
    fine: str
    classpath: str
    unspsc: str | None = None


class Extraction(BaseModel):
    item_type: str
    series: str | None = None
    classpath: str | None = None       # extractor may classify inline (cloud path)
    unspsc: str | None = None
    official_domain: str | None = None
    brand: str | None = None          # brand as printed on the product (e.g. 3M)
    brand_inferred: bool = False      # True when brand came from model-code knowledge
    manufacturer: str | None = None   # actual manufacturer, may differ from supplier
    attributes: list[Attribute] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    application: str | None = None
    includes: str | None = None
    additional: str | None = None


class RetrievalResult(BaseModel):
    domain: str | None = None
    mfr_url: str | None = None
    product_url: str | None = None  # deep link to the exact product page
    ref_urls: list[str] = Field(default_factory=list)
    snippets: list[Evidence] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class PhysicsCheck(BaseModel):
    name: str
    status: str  # SAT | UNSAT | SKIPPED
    fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class PhysicsReport(BaseModel):
    family: str
    checks: list[PhysicsCheck] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "UNSAT" for c in self.checks)

    @property
    def violated_fields(self) -> set[str]:
        out: set[str] = set()
        for check in self.checks:
            if check.status == "UNSAT":
                out.update(check.fields)
        return out


class RowResult(BaseModel):
    mfg_part_num: str
    clean: CleanRow
    classification: Classification | None = None
    retrieval: RetrievalResult | None = None
    extraction: Extraction | None = None
    physics: PhysicsReport | None = None
    output_row: dict[str, str] = Field(default_factory=dict)
    triage_score: float = 0.0
    flags: list[str] = Field(default_factory=list)
