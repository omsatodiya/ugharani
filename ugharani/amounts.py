import re

# Matches ASCII or native-script digit runs with optional Indian/Western commas, e.g. 2,40,000
_NUMBER = re.compile(r"\d[\d,]*")


def find_amounts(text: str) -> list[int]:
    """Return every integer that appears in text (commas stripped)."""
    return [int(m.replace(",", "")) for m in _NUMBER.findall(text) if m.replace(",", "")]
