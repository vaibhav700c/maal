"""Pipeline configuration loaded from .env / environment."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Settings:
    api_key: str
    model: str
    rpm: int
    input_csv: Path
    expected_headers_csv: Path
    output_dir: Path
    model_fallbacks: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(ROOT / ".env")
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            model_fallbacks=[
                m.strip()
                for m in os.environ.get("GEMINI_MODEL_FALLBACKS", "").split(",")
                if m.strip()
            ],
            rpm=int(os.environ.get("RPM_LIMIT", "10")),
            input_csv=ROOT / "input" / "Unihack_ Sample Dataset - Input.csv",
            expected_headers_csv=ROOT
            / "input"
            / "Unihack_ Expected Output - Delivery Format.csv",
            output_dir=ROOT / "output",
        )
