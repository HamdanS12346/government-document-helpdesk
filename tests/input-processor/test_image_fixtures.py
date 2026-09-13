"""Image fixture inventory tests for the Input Processor."""

from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError


FIXTURES = Path(__file__).parent / "fixtures" / "images"

TASK_10_FIXTURES = {
    "IMG-001": FIXTURES / "valid" / "img_001_clear_form.png",
    "IMG-002": FIXTURES / "blank" / "img_002_blank_no_text.png",
    "IMG-003": FIXTURES / "blurry" / "img_003_blurry_form.png",
    "IMG-004": FIXTURES / "unreadable" / "img_004_severely_unreadable.png",
    "IMG-005": FIXTURES / "pii" / "img_005_fictional_pii.png",
    "IMG-006": FIXTURES / "instructions" / "img_006_legitimate_instructions.png",
    "IMG-007": FIXTURES / "injection" / "img_007_ai_directed_text.png",
    "IMG-008-invalid": FIXTURES / "invalid" / "img_008_invalid_image_bytes.png",
    "IMG-008-unsupported": FIXTURES / "unsupported" / "img_008_unsupported_format.gif",
}


def test_task_10_image_fixtures_exist() -> None:
    missing = [
        fixture_id for fixture_id, path in TASK_10_FIXTURES.items() if not path.exists()
    ]

    assert missing == []


@pytest.mark.parametrize(
    "fixture_id,path",
    [
        item
        for item in TASK_10_FIXTURES.items()
        if item[0] not in {"IMG-008-invalid", "IMG-008-unsupported"}
    ],
)
def test_supported_task_10_image_fixtures_are_openable(
    fixture_id: str,
    path: Path,
) -> None:
    with Image.open(path) as image:
        image.verify()

    assert fixture_id.startswith("IMG-")


def test_img_008_invalid_image_bytes_are_not_openable() -> None:
    with pytest.raises(UnidentifiedImageError):
        Image.open(TASK_10_FIXTURES["IMG-008-invalid"])


def test_img_008_unsupported_fixture_uses_gif_format() -> None:
    with Image.open(TASK_10_FIXTURES["IMG-008-unsupported"]) as image:
        assert image.format == "GIF"
