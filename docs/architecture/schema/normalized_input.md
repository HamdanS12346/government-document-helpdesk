# Normalized Input

## Overview

`NormalizedInput` is the standardized representation of everything provided by the user at the start of the workflow.

The user can provide:

* Text query
* One or more images
* One or more PDFs
* One or more spreadsheets, once `.xlsx` processing is implemented
* A combination of the above

The Input Processor is responsible for processing these inputs and producing a single `NormalizedInput` object.

The purpose of normalization is to give downstream nodes a consistent structure regardless of how the user provided the input.

Downstream nodes should not need to handle raw file types or modality-specific input handling.

---

## Schema

```text
NormalizedInput
|-- user_query: str
|-- image_content: List[ImageContent]
|-- pdf_content: List[PDFContent]
|-- spreadsheet_content: List[SpreadsheetContent]
`-- combined_text: str
```

### `user_query`

```text
user_query: str
```

The text entered directly by the user.

---

### `image_content`

```text
image_content: List[ImageContent]
```

A list containing the processed content of all images attached by the user. If no images are provided, this is `[]`.

```text
ImageContent
|-- image_name: str
|-- extracted_text: str
`-- preview: str
```

The preview is intended to be lightweight and should not be an LLM-generated summary.

---

### `pdf_content`

```text
pdf_content: List[PDFContent]
```

A list containing the processed content of all PDFs attached by the user. If no PDFs are provided, this is `[]`.

```text
PDFContent
|-- pdf_name: str
|-- extracted_text: str
`-- preview: str
```

The preview is intended to be lightweight and should not be an LLM-generated summary.

---

### `spreadsheet_content`

```text
spreadsheet_content: List[SpreadsheetContent]
```

A list containing the processed content of all supported spreadsheets attached by the user. If no spreadsheets are provided, or spreadsheet processing has not produced successful spreadsheet output, this is `[]`.

Each spreadsheet is represented by a `SpreadsheetContent` object. The contract is provider-independent and serializable. It must not contain `openpyxl` objects, workbook objects, worksheet objects, cell objects, file handles, temporary paths, raw bytes, or unmasked PII.

```text
SpreadsheetContent
|-- workbook_name: str
|-- sheets: List[SpreadsheetSheet]
|-- preview: str
|-- warnings: List[str]
`-- metadata: SpreadsheetMetadata
```

```text
SpreadsheetSheet
|-- name: str
|-- position: int
|-- max_row: int
|-- max_column: int
|-- is_empty: bool
|-- cells: List[SpreadsheetCell]
|-- merged_ranges: List[str]
`-- tables: List[SpreadsheetTable]
```

```text
SpreadsheetCell
|-- coordinate: str
|-- row: int
|-- column: int
|-- value: str | int | float | bool | null
|-- value_type: str
|-- formula: str | null
|-- cached_value: str | int | float | bool | null
`-- truncated: bool
```

```text
SpreadsheetTable
|-- name: str
|-- reference: str
`-- columns: List[str]
```

```text
SpreadsheetMetadata
|-- workbook_name: str
|-- processed_sheet_count: int
|-- total_visible_sheet_count: int
|-- hidden_sheet_count: int
|-- max_sheets: int
|-- max_rows_per_sheet: int
|-- max_columns_per_sheet: int
|-- max_text_cell_characters: int
`-- preview_row_count: int
```

Spreadsheet metadata records safe counts and the limits applied while processing. It must not include raw workbook bytes, parser objects, internal paths, or raw cell values.

Formula cells keep formula text separate from cached/displayed values. Cached values must not be described as freshly calculated.

---

### `combined_text`

```text
combined_text: str
```

A combined textual representation of the normalized input.

It can contain:

* The user's query
* Extracted image content
* Extracted PDF content
* A deterministic projection of successful spreadsheet content

`combined_text` should not replace the structured `image_content`, `pdf_content`, and `spreadsheet_content` fields. Those fields remain available when modality-specific information is required.

---

## Examples

### Text Only

```text
NormalizedInput(
    user_query="What documents are required for PAN application?",
    image_content=[],
    pdf_content=[],
    spreadsheet_content=[],
    combined_text="<USER_QUERY>\nWhat documents are required for PAN application?"
)
```

### User Query + One Spreadsheet

```text
NormalizedInput(
    user_query="Explain this workbook.",
    image_content=[],
    pdf_content=[],
    spreadsheet_content=[
        SpreadsheetContent(
            workbook_name="applications.xlsx",
            sheets=[...],
            preview="Workbook: applications.xlsx\nSheet: Applicants",
            warnings=[],
            metadata=SpreadsheetMetadata(...)
        )
    ],
    combined_text="..."
)
```

---

## Design Principle

The `NormalizedInput` contract provides a consistent boundary between the Input Processor and the rest of the workflow.

The Input Processor handles:

```text
Raw User Input
      |
      v
Processing / Extraction
      |
      v
NormalizedInput
```

After this point, downstream nodes work with the normalized structure rather than dealing directly with raw text, images, PDFs, or spreadsheets.

The detailed implementation of text extraction, OCR, PDF parsing, spreadsheet parsing, preview generation, and other modality-specific processing belongs inside the Input Processor and its processors. The contract above defines only what the Input Processor exposes to the rest of the system.
