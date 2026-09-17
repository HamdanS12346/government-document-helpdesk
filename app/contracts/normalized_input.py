"""Normalized input contract definitions."""

from pydantic import BaseModel, ConfigDict, Field


SpreadsheetCellValue = str | int | float | bool | None


class ImageContent(BaseModel):
    """Processed content extracted from one uploaded image."""

    model_config = ConfigDict(extra="forbid")

    image_name: str
    extracted_text: str
    preview: str


class PDFContent(BaseModel):
    """Processed content extracted from one uploaded PDF."""

    model_config = ConfigDict(extra="forbid")

    pdf_name: str
    extracted_text: str
    preview: str


class SpreadsheetCell(BaseModel):
    """Bounded, provider-independent content from one spreadsheet cell."""

    model_config = ConfigDict(extra="forbid")

    coordinate: str
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    value: SpreadsheetCellValue = None
    value_type: str
    formula: str | None = None
    cached_value: SpreadsheetCellValue = None
    truncated: bool = False


class SpreadsheetTable(BaseModel):
    """Provider-independent Excel Table metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    reference: str
    columns: list[str] = Field(default_factory=list)


class SpreadsheetSheet(BaseModel):
    """Bounded content and structure extracted from one visible worksheet."""

    model_config = ConfigDict(extra="forbid")

    name: str
    position: int = Field(ge=1)
    max_row: int = Field(ge=0)
    max_column: int = Field(ge=0)
    is_empty: bool
    cells: list[SpreadsheetCell] = Field(default_factory=list)
    merged_ranges: list[str] = Field(default_factory=list)
    tables: list[SpreadsheetTable] = Field(default_factory=list)


class SpreadsheetMetadata(BaseModel):
    """Safe workbook processing metadata for spreadsheet uploads."""

    model_config = ConfigDict(extra="forbid")

    workbook_name: str
    processed_sheet_count: int = Field(ge=0)
    total_visible_sheet_count: int = Field(ge=0)
    hidden_sheet_count: int = Field(ge=0)
    max_sheets: int = Field(ge=1)
    max_rows_per_sheet: int = Field(ge=1)
    max_columns_per_sheet: int = Field(ge=1)
    max_text_cell_characters: int = Field(ge=1)
    preview_row_count: int = Field(ge=0)


class SpreadsheetContent(BaseModel):
    """Processed content extracted from one uploaded spreadsheet workbook."""

    model_config = ConfigDict(extra="forbid")

    workbook_name: str
    sheets: list[SpreadsheetSheet] = Field(default_factory=list)
    preview: str
    warnings: list[str] = Field(default_factory=list)
    metadata: SpreadsheetMetadata


class NormalizedInput(BaseModel):
    """Normalized user text and successfully processed attachments."""

    model_config = ConfigDict(extra="forbid")

    user_query: str
    image_content: list[ImageContent]
    pdf_content: list[PDFContent]
    spreadsheet_content: list[SpreadsheetContent] = Field(default_factory=list)
    combined_text: str


__all__ = [
    "ImageContent",
    "NormalizedInput",
    "PDFContent",
    "SpreadsheetCell",
    "SpreadsheetCellValue",
    "SpreadsheetContent",
    "SpreadsheetMetadata",
    "SpreadsheetSheet",
    "SpreadsheetTable",
]
