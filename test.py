r"""Manual Excel Input Processor runner.

Run:

    .\.venv\Scripts\python.exe test.py
"""

from pathlib import Path

from app.input_processing.processors import process_input
from app.input_processing.schemas import Attachment, InputRequest


PROJECT_ROOT = Path(__file__).resolve().parent
WORKBOOK_PATH = PROJECT_ROOT / "tests" / "input-processor" / "fixtures" / "spreadsheets" / "aadhar_update.xlsx"
SPREADSHEET_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def main() -> int:
    user_query = input("Text query (optional): ").strip() or None
    request = InputRequest(
        user_query=user_query,
        attachments=[
            Attachment(
                filename=WORKBOOK_PATH.name,
                media_type=SPREADSHEET_MEDIA_TYPE,
                content=WORKBOOK_PATH.read_bytes(),
            )
        ],
    )
    result = process_input(request)

    if result.normalized_input is not None:
        print(result.normalized_input.model_dump_json(indent=2))
        return 0

    print(result.model_dump_json(indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
