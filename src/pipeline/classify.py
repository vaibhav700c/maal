"""Batched taxonomy classification (Dept/Class/Fine/Classpath/UNSPSC)."""
from pipeline.models import CleanRow, Classification

SYSTEM = (
    "You are an industrial product taxonomy specialist for a distributor "
    "catalog. Classify each row into Dept > Class > Fine and a full "
    "classpath. Use standard distributor taxonomy (e.g. Appliances & "
    "Consumer Electronics>Kitchen Appliances>Built-In Dishwashers) and the "
    "6-digit UNSPSC code when confident. Output STRICT JSON only."
)

PROMPT_TEMPLATE = """Classify each numbered catalog row. Output a STRICT JSON array with exactly one object per input index, same order:
[{{"index": 0, "dept": "...", "klass": "...", "fine": "...", "classpath": "Dept>Class>Fine", "unspsc": "123456 or null"}}]

Example (ground truth):
row: PDSH4816AF Dishwasher SS - Display Only [mfr: Appliance Dealers Cooperative]
-> {{"index":0,"dept":"Appliances","klass":"Large Appliances","fine":"Dishwashers","classpath":"Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers","unspsc":"42172203"}}

Rows:
{rows}"""


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _parse(item: dict) -> Classification | None:
    if not isinstance(item, dict):
        return None
    classpath = str(item.get("classpath") or "").strip()
    if not classpath:
        return None
    parts = [p.strip() for p in classpath.split(">")]
    return Classification(
        dept=str(item.get("dept") or (parts[0] if parts else "")),
        klass=str(item.get("klass") or (parts[1] if len(parts) > 1 else "")),
        fine=str(item.get("fine") or (parts[-1] if parts else "")),
        classpath=classpath,
        unspsc=str(item["unspsc"]) if item.get("unspsc") else None,
    )


async def classify_rows(
    llm, clean_rows: list[CleanRow], batch: int = 20
) -> dict[str, Classification]:
    """Returns mapping mfg_part_num -> Classification; rows that fail are omitted."""
    result: dict[str, Classification] = {}
    for chunk in _chunk(clean_rows, batch):
        listing = "\n".join(
            f'{i}: {r.part_desc} [mfr: {r.mfr_name or "unknown"}]'
            for i, r in enumerate(chunk)
        )
        data = await llm.generate_json(PROMPT_TEMPLATE.format(rows=listing), SYSTEM)
        items = data if isinstance(data, list) else data.get("rows", [])
        by_index = {}
        for item in items:
            if isinstance(item, dict) and "index" in item:
                try:
                    by_index[int(item["index"])] = item
                except (TypeError, ValueError):
                    continue
        for i, row in enumerate(chunk):
            parsed = _parse(by_index.get(i))
            if parsed is not None:
                result[row.mfg_part_num] = parsed
    return result
