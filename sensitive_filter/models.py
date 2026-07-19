from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Match:
    word: str
    category: str
    level: int
    start: int
    end: int
    matched_text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScanResult:
    text: str
    matches: list[Match]

    @property
    def sensitive(self) -> bool:
        return bool(self.matches)

    def to_dict(self) -> dict:
        return {
            "sensitive": self.sensitive,
            "count": len(self.matches),
            "matches": [item.to_dict() for item in self.matches],
        }

