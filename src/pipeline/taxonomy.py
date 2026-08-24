"""Unilog internal Dept/Class/Fine taxonomy mapping.

The public Classpath (what distributors see) differs from Unilog's internal
Dept > Class > Fine hierarchy used in the Delivery Format. This table maps
the catalog's product families to that internal taxonomy; unmatched products
fall back to their public classpath parts.
"""
import re

# keyword -> (Dept, Class, Fine); first match wins (checked in order)
UNILOG_TAXONOMY: list[tuple[str, str, str, str]] = [
    # appliances
    ("dishwasher", "Appliances", "Large Appliances", "Dishwashers"),
    ("refrigerator|fridge", "Appliances", "Large Appliances", "Refrigerators"),
    ("freezer", "Appliances", "Large Appliances", "Freezers"),
    ("dryer", "Appliances", "Large Appliances", "Clothes Dryers"),
    ("washer|laundry", "Appliances", "Large Appliances", "Clothes Washers"),
    ("microwave|otr microwave", "Appliances", "Large Appliances", "Microwaves"),
    ("range|cooktop|oven", "Appliances", "Large Appliances", "Ranges & Ovens"),
    ("beverage center|coffee|espresso|toaster", "Appliances", "Small Appliances", "Kitchen Appliances"),
    # lighting
    ("chandelier|pendant", "Lighting", "Decorative Lighting", "Chandeliers & Pendants"),
    ("wall light|wall lt|sconce|ext wall", "Lighting", "Outdoor Lighting", "Wall Lights"),
    ("ceiling light|downlight|flat panel|highbay", "Lighting", "Commercial Lighting", "Ceiling Lights"),
    ("led bulb|incan|halogen|bulb|lamp a19|mr16|par38|br30", "Lighting", "Lamps", "LED Lamps"),
    ("flashlight|headlight|clip light|work light|shop light", "Lighting", "Portable Lighting", "Flashlights & Work Lights"),
    ("tape light|strip light", "Lighting", "Accent Lighting", "Tape & Strip Lights"),
    ("motion light", "Lighting", "Outdoor Lighting", "Security Lights"),
    # abrasives / cutting
    ("cut off disc|cut-off disc|cut off wheel|metal cut", "Tools", "Abrasives", "Cut-Off Wheels"),
    ("grinding wheel", "Tools", "Abrasives", "Grinding Wheels"),
    ("masonry cut|masonry grind", "Tools", "Abrasives", "Masonry Wheels"),
    ("sanding belt", "Tools", "Abrasives", "Sanding Belts"),
    ("sandpaper|stikit|abrasive sheet|sanding sponge|abranet|hiolit", "Tools", "Abrasives", "Sandpaper & Sheets"),
    ("saw blade|circ saw|miter saw blade|track saw", "Tools", "Accessories", "Saw Blades"),
    ("jig saw blade|recip blade|bandsaw blade", "Tools", "Accessories", "Blade Accessories"),
    ("router bit|plug cutter|countersink", "Tools", "Accessories", "Router Bits"),
    ("planer blade|dado", "Tools", "Accessories", "Planer Accessories"),
    ("diamond.*blade|tile blade", "Tools", "Accessories", "Diamond Blades"),
    ("hole dozer|hole saw", "Tools", "Accessories", "Hole Saws"),
    # fasteners
    ("nailer|brad nailer|framing nailer", "Tools", "Pneumatic Tools", "Nailers"),
    ("finish nail|brad bb|staple\b", "Hardware", "Fasteners", "Nails & Staples"),
    # tools
    ("drill|hammer drill", "Tools", "Power Tools", "Drills"),
    ("impact driver|impact wrench", "Tools", "Power Tools", "Impact Tools"),
    ("sander|polisher", "Tools", "Power Tools", "Sanders"),
    ("grinder|die grinder", "Tools", "Power Tools", "Grinders"),
    ("router\b|plunge.*router", "Tools", "Power Tools", "Routers"),
    ("jig saw|recip saw|circular saw|miter saw|table saw|track saw|band saw", "Tools", "Power Tools", "Saws"),
    ("screwdriver|bit holder|drive bit|torsion bit|socket adapter", "Tools", "Hand Tools", "Screwdriving"),
    ("ratchet|wrench set|mechanics set|universal joint", "Tools", "Hand Tools", "Wrenches & Sockets"),
    ("laser|line laser", "Tools", "Measuring & Layout", "Lasers"),
    ("rafter square|t-square|bigcal|caliper", "Tools", "Measuring & Layout", "Layout Tools"),
    ("voltage detector", "Tools", "Electrical Tools", "Testers"),
    ("fence|xtender|sled|align-a-saw", "Tools", "Table Saw Accessories", "Fences & Guides"),
    ("tool chest|packout|organizer|starter kit|battery|charger", "Tools", "Tool Storage & Power", "Batteries & Storage"),
    ("grease gun|blower|trimmer|vacuum|speaker", "Tools", "Outdoor Power Equipment", "OPE & Site Gear"),
    # safety
    ("safety glasses|hearing protector", "Safety", "Personal Protective Equipment", "Eye & Ear Protection"),
    ("glove|hoodie", "Safety", "Workwear", "Heated Workwear"),
    ("fire extinguisher", "Safety", "Fire Safety", "Extinguishers"),
    ("smoke|co alarm", "Safety", "Fire Safety", "Alarms"),
    # electrical
    ("gfci|outlet|receptacle|switch|dimmer|timer|wallplate|box cover|load center|cord grip", "Electrical", "Wiring Devices", "Wiring Devices"),
    ("wire|cable|cord\b", "Electrical", "Wire & Cable", "Conductor"),
    # building materials
    ("decking|fascia|rail kit|post sleeve|post cap|baluster|railing|joist tape|post wrap", "Building Materials", "Decking & Railing", "Deck Components"),
    ("vinyl plank|laminate|hardwood|drywall|osb|sheathing|plywood", "Building Materials", "Interior Finishes", "Panel Goods"),
    ("hardiepanel|smart lap|smartside|soffit|siding", "Building Materials", "Exterior Cladding", "Siding & Trim"),
    ("mortar", "Building Materials", "Concrete & Mortar", "Colored Mortar"),
    ("skylight|patio dr|hopper|slider window", "Building Materials", "Windows & Doors", "Skylights & Patio Doors"),
    ("threshold|hanger|attic access", "Building Materials", "Millwork & Hardware", "Door Hardware"),
    ("ice guard|rainscreen|eaveguard", "Building Materials", "Roofing", "Roof Underlayment"),
    ("post sleeve|support post", "Building Materials", "Structural", "Posts & Columns"),
    # plumbing fixtures
    ("faucet|sink\b", "Plumbing", "Kitchen & Bath", "Faucets"),
]

# supplier-name based corrections (distributor vs maker disambiguation)


def normalize_classpath(classpath: str | None) -> str:
    """Canonical '>' separator. LLM classifications drift between
    'A / B / C', 'A > B' and 'A>B'; downstream Dept/Class/Fine splitting
    only understands '>', so everything normalizes here."""
    if not classpath:
        return ""
    parts = [p.strip() for p in re.split(r"\s*(?:/|>|->)\s*", str(classpath)) if p.strip()]
    return ">".join(parts)


# Fallback models answer 'Generic'/'Unbranded' when they don't know a
# brand; such placeholders must never occupy the brand slot or real
# hints (DIB_Brand, supplier-as-maker) can't flow through.
GENERIC_BRAND_TOKENS = {
    "generic", "unbranded", "oem", "nobrand", "none", "unknown",
    "replacement", "aftermarket", "universal",
}


def is_generic_brand(brand: str | None) -> bool:
    n = re.sub(r"[^a-z0-9]+", "", (brand or "").lower())
    return n in {re.sub(r"[^a-z0-9]+", "", t) for t in GENERIC_BRAND_TOKENS}


def dept_class_fine(text: str) -> tuple[str | None, str | None, str | None]:
    """Map free text (classpath leaf or description) to internal taxonomy."""
    low = text.lower()
    for pattern, dept, klass, fine in UNILOG_TAXONOMY:
        if re.search(pattern, low):
            return dept, klass, fine
    return None, None, None


def apply_unilog_taxonomy(classpath: str | None, item_type: str | None) -> dict:
    """Returns {dept, klass, fine} preferring keyword match over raw parts."""
    for source in (item_type or "", normalize_classpath(classpath)):
        d, k, f = dept_class_fine(source)
        if d:
            return {"dept": d, "klass": k, "fine": f}
    parts = [p.strip() for p in normalize_classpath(classpath).split(">") if p.strip()]
    return {
        "dept": parts[0] if parts else "",
        "klass": parts[1] if len(parts) > 1 else parts[0] if parts else "",
        "fine": parts[-1] if parts else "",
    }


# ---------------------------------------------------------------------------
# Brand -> corporate parent entity mapping.
# Source: public corporate ownership records; matches Unilog's own usage
# (e.g. Frigidaire products list "Rheem Manufacturing" as MANUFACTURER_NAME).
# ---------------------------------------------------------------------------
CORPORATE_PARENT: dict[str, str] = {
    "frigidaire": "Rheem Manufacturing",
    "whirlpool": "Whirlpool Corporation",
    "maytag": "Whirlpool Corporation",
    "kitchenaid": "Whirlpool Corporation",
    "jenn-air": "Whirlpool Corporation",
    "amana": "Whirlpool Corporation",
    "ge": "GE Appliances",
    "hotpoint": "GE Appliances",
    "cafe": "GE Appliances",
    "profile": "GE Appliances",
    "lg": "LG Electronics",
    "samsung": "Samsung Electronics",
    "bosch": "BSH Home Appliances",
    "thermador": "BSH Home Appliances",
    "beko": "Arçelik",
    "element": "Element Electronics",
    "diablo": "Freud Inc",
    "freud": "Freud Inc",
    "milwaukee": "Milwaukee Tool",
    "makita": "Makita Corporation",
    "dewalt": "Stanley Black & Decker",
    "black & decker": "Stanley Black & Decker",
    "bostitch": "Stanley Black & Decker",
    "lenox": " Stanley Black & Decker",
    "irwin": "Irwin Industrial Tools",
    "satco": "Satco Products Inc",
    "nuvo": "Satco Products Inc",
    "kichler": "Kichler Lighting",
    "leviton": "Leviton Manufacturing",
    "lutron": "Lutron Electronics",
    "trex": "Trex Company",
    "timbertech": "AZEK Building Products",
    "azek": "AZEK Building Products",
    "festool": "TTS Tooltechnic Systems",
    "3m": "3M Company",
    "paslode": "Illinois Tool Works",
    "senco": "Senco Brands",
    "senco products": "Senco Brands",
}


def corporate_parent(brand: str | None) -> str | None:
    """Look up the corporate parent entity for a brand name."""
    if not brand:
        return None
    low = brand.replace("\u00ae", "").replace("\u2122", "").strip().lower()
    return CORPORATE_PARENT.get(low)


# ---------------------------------------------------------------------------
# Industry-standard catalog abbreviations (reverse-engineered from Unilog GT).
# Used by the invoice description builder to pack specs into ≤40 chars.
# ---------------------------------------------------------------------------
CATALOG_ABBREVIATIONS: dict[str, str] = {
    # materials / finishes
    "stainless steel": "SST",
    "stainless": "SST",
    "black on light tan": "BLTLN",
    "black on white": "BLWH",
    "black on black": "BLBL",
    "white on white": "WHWH",
    "bisque": "BISQ",
    "black": "BLK",
    "white": "WHT",
    "gray": "GRY",
    "grey": "GRY",
    "chrome": "CHR",
    "brushed nickel": "BNKL",
    "polished nickel": "PNKL",
    "satin nickel": "SNKL",
    "vibrant stainless": "VSTL",
    "spotshield stainless": "SPSTL",
    # mounting / installation
    "built-in": "BLTIN",
    "portable": "PRTBL",
    "countertop": "CNTRT",
    "undercounter": "UNDCN",
    "leg": "LEG",
    "tile": "TILE",
    # product types
    "dishwasher": "DISHWASHER",
    "refrigerator": "REFRIGERATOR",
    "dryer": "DRYER",
    "washer": "WASHER",
    "microwave": "MICROWAVE",
    "range": "RANGE",
}

# GT attribute label ordering — the sequence Unilog expects per category.
# Used to sort extracted attributes so they appear in the expected positions.
GT_ATTR_ORDER: dict[str, list[str]] = {
    "dishwasher": [
        "Series", "Model", "Number of Wash Cycles", "Voltage Rating",
        "Amperage Rating", "Mounting Type", "Plug Type", "Size",
        "Depth With Door Open", "Minimum Height", "Maximum Height",
        "Sound Level", "Material", "Color", "Additional Information",
    ],
    "cut-off wheel": [
        "Diameter", "Thickness", "Arbor", "Material", "Max RPM",
        "Application", "Grit",
    ],
    "light bulb": [
        "Wattage", "Color Temperature", "Base Type", "Shape", "Dimmable",
    ],
    "_default": [
        "Series", "Model Number", "Brand Name", "Voltage Rating",
        "Amperage Rating", "Mounting Type", "Sound Level", "Material",
        "Color", "Size", "Additional Information",
    ],
}


def order_attributes(attrs: list, item_type: str) -> list:
    """Sort attributes to match GT label ordering for this product family."""
    low_type = (item_type or "").lower()
    template = None
    for key, order in GT_ATTR_ORDER.items():
        if key != "_default" and key in low_type:
            template = order
            break
    if not template:
        template = GT_ATTR_ORDER["_default"]

    def sort_key(attr):
        low = attr.label.lower()
        for i, t in enumerate(template):
            if t.lower() == low or t.lower() in low:
                return i
        return len(template)

    return sorted(attrs, key=sort_key)
