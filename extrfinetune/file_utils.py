"""File discovery helpers shared by the extraction stages."""

from pathlib import Path
from typing import List


def list_visible_text_files(folder: str) -> List[str]:
    """Return deterministic real text inputs, excluding macOS AppleDouble files."""
    root = Path(folder)
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".txt"
        and not path.name.startswith(".")
        and not path.name.startswith("._")
    )
