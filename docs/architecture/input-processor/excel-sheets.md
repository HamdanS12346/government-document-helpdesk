# Excel / Spreadsheet Input Architecture

## 1. Purpose

This document defines the proposed architecture for adding spreadsheet uploads to the existing Input Processor. It is an implementation-planning reference: it records confirmed MVP decisions, contracts, ownership, processing stages, security rules, tests, open decisions, and delivery phases.

Spreadsheet support is an extension of the existing multimodal architecture, not a separate subsystem. The design keeps GraphState independent of `openpyxl`, treats uploads as request-scoped user content, and preserves the existing privacy and guardrail boundaries.

## 2. Status and Scope

Project architecture: version 0.1. Project phase: research and planning. Spreadsheet implementation has not started.

The spreadsheet MVP supports `.xlsx` workbooks for public-citizen use cases in English. The broader product targets common government documents and services in India. Official sources remain authoritative for government facts and procedures; an uploaded workbook is user-provided evidence, not government knowledge.

The existing Input Processor remains the only boundary for uploaded content. The existing text, image, PDF, GraphState, intent, retrieval, response, and memory contracts should change only where the spreadsheet extension requires an explicit contract update.

## 3. Confirmed MVP Decisions

The following decisions are confirmed:

- Support `.xlsx` only.
- Process no more than five worksheets per workbook.
- Process no more than 50 rows and 50 columns per worksheet.
- Limit textual content from an individual cell to 5,000 characters.
- Process all permitted visible worksheets in workbook order.
- Preserve empty worksheets.
- Exclude hidden worksheet content and do not intentionally include hidden rows or columns.
- Preserve formulas and cached/displayed values separately when available.
- Preserve merged ranges and Excel Table metadata where available.
- Include processed spreadsheet content in `combined_text`.
- Mask PII at the cell/value level.
- Generate a deterministic bounded preview without an LLM.
- Keep protected/encrypted workbooks and `.xlsm` support outside the MVP.
- Do not add uploads to the knowledge base, vector store, or long-term memory automatically.
- Discard raw workbook data after request processing.

## 4. Existing Architecture

The current high-level flow is:

```text
User request
    -> Input Processor
    -> NormalizedInput
    -> Intent Classifier
    -> Retriever / Clarification / Response
```

`app/input_processing/processors.py` is the public orchestrator and modality router. Image and PDF modules own their modality-specific work. The processor returns normalized content plus structured attachment status. Downstream components must not depend on API upload classes, raw bytes, temporary paths, or modality-provider objects.

The spreadsheet extension follows this same boundary:

```text
Attachment bytes
    -> generic validation
    -> .xlsx routing
    -> workbook validation
    -> spreadsheet parser provider
    -> bounded visible-sheet extraction
    -> truncation and PII masking
    -> structured normalization
    -> deterministic preview and text projection
    -> NormalizedInput
```

The graph does not parse workbooks or import `openpyxl`. It consumes only serializable normalized content.

## 5. Ownership Boundaries

### 5.1 Input Processor orchestrator

`processors.py` owns attachment-level validation, modality identification, dispatch, sequential multi-attachment orchestration, result aggregation, partial-success behavior, `NormalizedInput` construction, safe errors, warnings, and cleanup.

It must not inspect workbook cells, calculate formulas, generate spreadsheet previews, or implement spreadsheet-specific PII masking.

### 5.2 Spreadsheet processor

The proposed module is `app/input_processing/excel_processor.py`; the exact name may change to match repository conventions. It owns workbook validation, provider invocation, visible worksheet selection, bounded cell extraction, formula/cached-value handling, merged ranges, tables, truncation, spreadsheet normalization, preview generation, and the spreadsheet `combined_text` projection.

### 5.3 Guardrails

Reusable input guardrails own generic validation and PII policy. Spreadsheet extraction remains in the spreadsheet processor. Prompt-injection defense belongs to the broader untrusted-content and response architecture, not to keyword rejection in the parser.

### 5.4 Downstream components

The Intent node consumes normalized content and bounded preview context. The Context Builder may use uploaded spreadsheet content if upload-aware context is approved. The Retriever remains responsible for authoritative government sources. The response layer distinguishes uploaded evidence from official sources and owns citation behavior.

## 6. Input Contract

The public request remains conceptually:

```text
InputRequest
├── user_query: optional str
└── attachments: list[Attachment]
```

```text
Attachment
├── filename: str
├── media_type: str
└── content: bytes
```

Attachments cross the processor boundary as transient bytes. The processor must not require filesystem paths, frontend upload objects, or permanent object-storage references. Attachment-only, text-only, and mixed-modality requests remain valid.

The caller creates the request. The Input Processor owns transient processing and disposal. Raw bytes are not retained after processing.

## 7. NormalizedInput Extension

The existing contract is:

```text
NormalizedInput
├── user_query: str
├── image_content: list[ImageContent]
├── pdf_content: list[PDFContent]
└── combined_text: str
```

The proposed extension is:

```text
NormalizedInput
├── user_query: str
├── image_content: list[ImageContent]
├── pdf_content: list[PDFContent]
├── spreadsheet_content: list[SpreadsheetContent]
└── combined_text: str
```

Adding `spreadsheet_content` is a shared contract change and must be propagated deliberately through schemas, GraphState documentation, graph serialization, intent context, and tests. Existing fields and text/image/PDF behavior must not change silently.

`spreadsheet_content` is the authoritative normalized spreadsheet representation. `combined_text` is a deterministic projection for existing text-oriented components. Neither field may contain raw bytes, paths, file handles, parser objects, workbook objects, or unmasked PII.

## 8. Proposed SpreadsheetContent Schema

The exact Pydantic schema must be finalized before implementation. It must be serializable and independent of `openpyxl`.

Conceptually:

```text
SpreadsheetContent
├── workbook_name: str
├── sheets: list[SpreadsheetSheet]
├── preview: str
├── warnings: list[str]
└── metadata: SpreadsheetMetadata
```

```text
SpreadsheetSheet
├── name: str
├── position: int
├── max_row: int
├── max_column: int
├── is_empty: bool
├── cells: list[SpreadsheetCell]
├── merged_ranges: list[str]
└── tables: list[SpreadsheetTable]
```

```text
SpreadsheetCell
├── coordinate: str
├── row: int
├── column: int
├── value: JSON-compatible value or null
├── value_type: str
├── formula: str or null
├── cached_value: JSON-compatible value or null
└── truncated: bool
```

```text
SpreadsheetTable
├── name: str
├── reference: str
└── columns: list[str]
```

The schema may add provenance or warning fields after contract review, but it must not expose provider-specific types.

## 9. Value Semantics

String values remain strings after masking and truncation. Numeric values should retain numeric meaning. Boolean values remain boolean. Dates should retain an appropriate date or explicit serialized representation. Blank values must remain distinguishable from zero where practical. Error cells must be represented as errors rather than fabricated values.

Formula cells contain two separate concepts: the stored formula expression and the cached/displayed result. Both should be preserved when available without executing the formula. Cached values must be identified as cached/displayed values; the system must not claim they were freshly calculated. A missing cached value remains missing.

## 10. Parser Provider Boundary

`openpyxl` is the initial package candidate. It can inspect `.xlsx` structure without Microsoft Excel and expose worksheets, cells, formulas, merged ranges, and tables. It must remain behind a provider/processor boundary and must not leak workbook objects into shared contracts.

It must not execute formulas, VBA, macros, or embedded commands. The provider-facing interface should express extraction needs rather than expose library methods directly:

```python
class SpreadsheetParser(Protocol):
    def inspect(self, content: bytes, filename: str) -> ParsedWorkbook:
        ...
```

Provider output must be validated before normalization. Provider tests should use deterministic mocks where practical; real `.xlsx` fixtures should cover representative parser behavior. Changing the provider must not require changing GraphState or LangGraph nodes.

## 11. Dependency

The initial Python dependency candidate is `openpyxl` and belongs in the Python requirements set. It is distinct from image and scanned-PDF OCR dependencies and does not replace system-level OCR.

The accepted version should be pinned or bounded according to project policy. The implementation plan should include installation, import, and representative workbook tests. Parser behavior should be checked after dependency upgrades.

## 12. Attachment Validation

Validation must precede expensive extraction and must not trust the declared MIME type alone. It should consider filename extension, declared media type, file signature, file size, supported workbook type, and workbook structural limits.

The supported extension is `.xlsx`. `.xls`, `.xlsm`, empty files, invalid signatures, non-spreadsheet content renamed to `.xlsx`, corrupt packages, and unsupported workbook types must be rejected safely.

Validation errors must use the existing safe processor result contract. They must not contain raw cell values, stack traces, or sensitive package details. Validation failure must not invoke workbook extraction unnecessarily.

## 13. File Signature and Package Checks

An `.xlsx` file is an Office Open XML ZIP package. Signature validation should establish that the content is plausibly the expected package before workbook extraction. The implementation should also verify that required workbook structures can be opened by the parser.

Filename and MIME mismatches are failures unless the project-wide validation policy defines a safe normalization rule. Malformed archives and unexpected parser exceptions must become controlled errors rather than raw exceptions.

## 14. Workbook Limits

The existing upload-size limit remains in force. Spreadsheet-specific limits are:

```text
Maximum worksheets: 5
Maximum rows per worksheet: 50
Maximum columns per worksheet: 50
Maximum textual cell characters: 5,000
```

These limits are structural processing limits, not file-size limits. They must be configuration-driven and injectable in tests. The processor must not scan unbounded worksheet regions or allow content outside the configured bounds to enter output silently.

Recommended behavior is to reject a workbook exceeding the worksheet-count limit and, where safe, process bounded row/column content with a clear limitation warning. The selected behavior must be explicit in the shared result contract and consistent across validation, normalization, preview, and user-facing status.

## 15. Worksheet Processing

All permitted visible worksheets are processed in workbook order. Selection is deterministic and does not depend on the user query. Worksheet names, position, bounded dimensions, and empty status are preserved.

An empty worksheet is not an extraction failure. It remains identifiable in structured output and may receive a bounded empty-sheet marker in the preview and `combined_text`. A worksheet-level failure may coexist with successful worksheets only when partial success is safe and represented explicitly.

## 16. Hidden Content

Hidden worksheets are excluded from normal extracted content. Hidden rows and columns are not intentionally incorporated as visible content. Visibility metadata must be inspected before cell extraction.

Excluded content must not appear in structured output, preview, combined text, warnings, logs, or telemetry. The processor must not modify the original workbook or selectively rewrite it; it simply avoids extracting excluded content. Visible content must continue to work when hidden content exists elsewhere.

## 17. Cell Extraction

Cells are extracted only within configured visible worksheet bounds. Each emitted cell should retain worksheet association, coordinate, row, column, typed value, formula information where present, and cached/displayed value where present.

The output should avoid materializing a full unbounded matrix. Empty cells should not create unnecessary serialized data, while merged structure must remain reconstructable. Extraction order must be deterministic. Values must be bounded and sanitized before entering normalized content.

## 18. Cell Character Limit

The 5,000-character limit applies to textual cell representation:

- Fewer than 5,000 characters are preserved.
- Exactly 5,000 characters are preserved without a truncation marker.
- More than 5,000 characters are truncated deterministically and marked incomplete.

The original value must not be retained after processing. PII detection must run on the bounded value that continues downstream. Warnings may include a count or safe cell location, but not raw content. Truncation occurs before preview and combined-text generation.

## 19. Formulas

Formula expressions are data and must remain data. The processor must not evaluate formulas, interpret them as prompts, or execute arbitrary instructions.

For a formula cell, normalized output preserves the formula field. If a cached/displayed result exists, it is preserved separately. If it does not exist, the cached field remains null or absent according to the schema. Formula errors remain distinguishable from ordinary strings, and cell references remain intact.

The textual projection should identify formula and cached value when both are available and should not imply that cached data was freshly calculated.

## 20. Merged Cells

Merged ranges are structural information and should be preserved. The anchor cell retains its value when one exists. Empty cells inside a merged range should not become independent meaningful values.

The normalized sheet should include range references such as `A1:C1`. Empty merged regions remain structurally represented. Horizontal merges, vertical merges, empty anchors, and merged section headings require tests. Full visual styling is out of scope.

## 21. Excel Tables

When Excel Table objects are available, preserve the table name, reference/boundary, column names, and containing worksheet. Table metadata coexists with ordinary cell extraction.

Table content must not be duplicated unnecessarily in `combined_text`. A worksheet without a Table remains valid. Failure to detect optional table metadata must not make ordinary worksheet content unusable unless the workbook itself is invalid. Synthetic table fixtures must verify names, boundaries, headers, and rows.

## 22. Formatting and Layout

The MVP preserves semantic structure, not pixel-perfect appearance. Required structure includes workbook name, worksheet order, rows and columns, coordinates, values, headers where present, formulas, cached values, merged ranges, and tables.

Full font, border, fill, image, and styling preservation is out of scope. Number formats should be considered when needed to avoid misleading values. Formatting must not unnecessarily expand the parser or normalized contract.

## 23. PII Processing

Spreadsheet values are untrusted user content. PII detection occurs after extraction and before normalized output is built. Masking operates at the cell/value level and preserves worksheet association, coordinates, row/column relationships, non-PII neighbors, table structure, and merged structure.

Raw PII must not enter `SpreadsheetContent`, `combined_text`, logs, traces, telemetry, memory, or retrieval stores. The exact detector and detector-failure policy remain open; the implementation plan must select or define the existing guardrail interface.

## 24. Prompt Injection and Untrusted Data

Spreadsheet content is data, not system instructions. Instruction-like text must not be rejected merely because it contains words such as "ignore". Legitimate government instructions remain valid cell content.

AI-directed text must not alter routing, tools, system instructions, or security policy. Formula strings must not execute. The parser must not invoke an LLM or tools based on cell text. The broader architecture should mark the content as user-provided or untrusted where provenance is supported.

## 25. Protected and Macro-Enabled Workbooks

Password-protected or encrypted workbook support is outside the MVP. Where reliably detectable, unsupported protection should produce a controlled result. The processor must not guess passwords or bypass encryption, and user-facing errors must not expose parser internals.

`.xlsm` is outside the supported format. Macro execution is never part of processing; VBA and embedded executable content must not run. `.xlsm` must not route to the `.xlsx` processor. Future support requires a separate security decision.

## 26. Structured Normalization

Normalization converts provider output into stable `SpreadsheetContent`. It must be deterministic for the same input and configuration and contain only bounded, masked, approved content.

It preserves worksheet order and names, cell coordinates and types, formulas, cached values, merged ranges, tables, empty sheets, and safe limitation warnings. It must not retain provider objects or raw workbook data.

## 27. Preview

The preview is a deterministic, lightweight representation for intent classification and routing. It is not the authoritative structured representation and is never generated by an LLM.

It contains a workbook overview plus bounded first-N content from each permitted visible worksheet. The overview should identify workbook name, sheet names, dimensions, and empty-sheet status. Samples should preserve headers where possible and use values already bounded and masked.

The preview excludes hidden content and must not include all workbook content. The value of N is an implementation parameter and must be configuration-visible. The preview format is not yet a public serialization contract.

Illustrative format:

```text
Workbook: applicants.xlsx
Sheets:
- Applicants: 40 rows x 8 columns
- Summary: 10 rows x 4 columns

Sheet: Applicants
Name | Age | State
[MASKED] | 25 | Goa

Sheet: Summary
Metric | Value
Applications | 125
```

## 28. Combined Text

Spreadsheet content must enter the existing `combined_text` field as a deterministic projection. It should include workbook context, worksheet names and order, row/column relationships, bounded values, formulas and cached values, useful table and merged-range context, empty-sheet markers, and safe limitation warnings.

It must contain masked values only, exclude hidden content and parser objects, remain bounded and deterministic, and avoid implying that cached formula values were freshly calculated. Existing image and PDF combined-text behavior must remain unchanged.

## 29. Provenance and Citation Boundary

An uploaded spreadsheet is not automatically authoritative. Answers based on it should identify it as user-provided evidence where the response contract supports provenance. Government factual claims still require authoritative retrieval and source references.

The spreadsheet processor does not create official citations. The Context Builder and response/citation layers own evidence presentation. Uploaded content and retrieved government content must remain distinguishable. Any future provenance field must not imply official government authority.

## 30. Knowledge-Base Boundary

Spreadsheet uploads are request-scoped user content. They must not enter the global knowledge base, ingestion pipeline, vector database, or long-term memory automatically. They may be used for the current request when upload-aware context is approved.

The Retriever remains responsible for official source retrieval. This separation prevents one user's spreadsheet from becoming shared knowledge.

## 31. Multiple Attachments

Sequential processing remains the initial preference. A request may contain text, images, PDFs, and spreadsheets. `processors.py` routes each attachment independently and collects successful results in deterministic input order.

A failed spreadsheet must not discard successful image or PDF content. If at least one usable modality succeeds, the result may be partial success. If every attachment fails and no usable text exists, the result is complete failure. `combined_text` includes successful normalized content only. Parallel processing can be introduced later without changing the public contract.

## 32. Failure Semantics

Failures use the existing safe result and error contracts. Relevant categories include unsupported extension or media type, invalid signature, empty content, corrupt workbook, unsupported protection, unsupported macro-enabled workbook, worksheet-count limit, row/column limit, cell truncation, provider unavailability, provider exception, worksheet extraction failure, PII detector failure, normalization failure, and unexpected processing failure.

Failure details must be safe for users and logs. Stack traces and sensitive values must not be exposed. Failures must not fabricate content. Partial worksheet success is allowed only when safe and explicitly represented.

## 33. Cleanup and Data Lifecycle

```text
receive transient bytes
    -> validate
    -> parse
    -> extract
    -> mask
    -> normalize
    -> use in current request
    -> discard raw workbook data
```

Cleanup must occur after success, validation failure, parser failure, PII or normalization failure, and unexpected exceptions. Any internal temporary file must be removed in a `finally` path. The preferred implementation avoids temporary files unless required by the provider.

The normalized object follows existing graph-state retention behavior; the raw workbook does not.

## 34. Privacy Requirements

Raw workbook bytes must not enter GraphState, logs, traces, memory, knowledge storage, vector storage, or long-term memory. Raw PII must not enter normalized output or telemetry. Cell values must not be logged for debugging, and errors must not echo sensitive values.

Operational metrics may contain counts and categories without content. Tests should inspect captured logs and trace-like payloads where those facilities exist.

## 35. Security Requirements

Workbooks are untrusted input. The processor must enforce resource limits before broad extraction, avoid unsafe path handling, contain parser exceptions, reject unsupported formats and invalid signatures, and prevent unbounded cell, worksheet, preview, and combined-text expansion.

It must not execute formulas, macros, VBA, embedded commands, or tools requested by cell text. It must not guess passwords or bypass protection. Security failures must fail safely and trigger cleanup.

## 36. Observability

Spreadsheet processing may emit safe metadata: modality, duration, worksheet counts, validation outcome, failure category, truncation count, masking count, formula-presence count, and table-detection outcome.

Telemetry must not include raw cell content, workbook bytes, or unmasked PII. Observability failures should not break processing unless policy requires it. The observability provider and redaction rules must be finalized before production.

## 37. Performance

Spreadsheet processing contributes to the broader normal-request target of roughly 5 to 6 seconds. Latency must be measured rather than assumed.

Measure a small workbook, multiple worksheets, the five-sheet boundary, maximum row/column dimensions, a large cell, formula-heavy content, table-heavy content, merged ranges, PII-heavy content, preview generation, normalization, combined-text generation, and end-to-end processor latency.

The configured limits provide predictable bounds, but no separate spreadsheet threshold is confirmed yet.

## 38. Configuration

Spreadsheet settings must be centralized and visible through configuration:

- Supported extension.
- Shared maximum upload size.
- Maximum worksheet count.
- Maximum rows per worksheet.
- Maximum columns per worksheet.
- Maximum textual cell characters.
- Preview sample size N.

Configuration must not contain secrets. Tests must be able to inject controlled values. Changing a limit must not require rewriting processor logic, and configuration changes must trigger relevant validation tests.

## 39. Intent Integration

The Intent classifier already consumes normalized input. The spreadsheet preview should provide bounded classification context for requests such as:

- "How many applications are in this sheet?"
- "Which applicants are from Goa?"
- "What does this column mean?"
- "Explain this spreadsheet."
- "What is the total shown in the summary?"

The classifier must not import `openpyxl`. It should consume normalized fields or the preview contract. Existing clarification behavior remains unchanged. Full structured content may be used later by context construction for cell-level reasoning.

## 40. RAG and Context Integration

An uploaded workbook may provide user-specific facts but does not become a RAG index document automatically. The Context Builder must distinguish upload evidence from retrieved authoritative sources.

For example, a workbook may contain an applicant status while an official source explains the applicable government procedure. The answer must not silently merge those evidence types. Any upload-aware retrieval strategy requires a separate downstream decision.

## 41. GraphState Integration

GraphState receives normalized input, not raw attachments. The expected integration is the extended `NormalizedInput` field. GraphState must not contain raw workbook bytes, temporary paths, file handles, `openpyxl` objects, provider responses, or unmasked PII.

Graph serialization must succeed with spreadsheet content. Existing image and PDF state behavior must remain compatible. Graph routing must not need spreadsheet-library knowledge.

## 42. API and Frontend Integration

The API continues to create the shared `Attachment` representation and must not call `excel_processor.py` directly. The public path remains:

```text
API request -> InputRequest -> process_input -> NormalizedInput
```

The frontend may advertise `.xlsx` only after backend support is ready. It should display safe validation, limitation, partial-success, and complete-failure messages. The API must not return raw workbook content unless a separate approved contract requires it.

## 43. Test Organization

Spreadsheet tests remain under the existing Input Processor test area. Provider-specific tests are isolated from orchestration tests. Public-boundary tests call `process_input`; provider tests may use mocks; integration tests use synthetic `.xlsx` fixtures.

Fixtures must not contain real citizen data, credentials, or private documents. Use fictional names, identifiers, and addresses for PII-like cases. Generate oversized payloads in test code where practical. Convert discovered defects into stable regression fixtures.

## 44. Validation Test Matrix

Cover at least:

- Valid `.xlsx` accepted.
- `.xls` and `.xlsm` rejected.
- Invalid signature under `.xlsx` rejected.
- Empty and corrupt workbooks rejected safely.
- Five-sheet workbook accepted; six-sheet workbook rejected.
- 50-row and 50-column boundaries accepted.
- 51-row and 51-column behavior follows configuration.
- Upload-size boundary enforced.
- Unsupported protection handled safely.
- Validation precedes expensive extraction.
- Validation logs contain no raw cell values.

## 45. Extraction Test Matrix

Cover workbook metadata, worksheet names and order, coordinates, strings, numbers, booleans, dates, blanks, errors, empty worksheets, all permitted visible worksheets, hidden worksheets, hidden rows, and hidden columns.

Verify deterministic extraction order and absence of excluded content from structured output, preview, and `combined_text`.

## 46. Formula and Structure Test Matrix

Formula tests verify formula text, cached value, distinction between formula and cached value, missing cached values, references, formula errors, non-execution, and deterministic combined text.

Structure tests verify horizontal and vertical merges, empty merged regions, anchor values, table names, table boundaries, table headers, table rows, and ordinary non-table worksheets.

## 47. Cell, Preview, and PII Test Matrix

Cell tests verify 4,999, 5,000, and 5,001-character values, deterministic truncation, truncation markers, bounded previews, and PII processing after bounding.

Preview tests verify overview, worksheet information, first-N content, headers, empty sheets, determinism, bounded size, and hidden-content exclusion.

PII tests verify detection in ordinary and table cells, position and structure preservation, neighboring non-PII preservation, and absence of raw PII from normalized output and combined text.

## 48. Prompt-Injection Test Matrix

Include legitimate instruction-like text and explicit AI-directed text. Both remain data rather than control instructions. Cell text must not change routing or trigger tools. Formula strings must not be interpreted as prompts. Naive keyword rejection must not be introduced. Downstream guardrails must preserve the instruction/data boundary.

## 49. Mixed-Modality Test Matrix

The public boundary should cover text plus spreadsheet, image plus spreadsheet, PDF plus spreadsheet, all four modalities, spreadsheet-only input, spreadsheet failure with successful image/PDF content, all attachments failing, successful spreadsheet content in `combined_text`, absence of raw bytes in GraphState, and deterministic routing order.

Existing text, image, and PDF tests must continue to pass.

## 50. Failure and Privacy Test Matrix

Failure tests cover provider unavailability, provider exceptions, malformed provider output, corrupt workbooks, worksheet failure, PII failure, normalization failure, unexpected exceptions, no fabricated content, safe messages, partial success, and complete failure.

Privacy tests cover cleanup after success, validation failure, parser failure, PII failure, and unexpected failure. They inspect logs and traces for raw values and unmasked PII.

## 51. Provider Abstraction Test Matrix

Provider tests verify successful extraction, parser failures, and malformed provider output. Orchestration tests use parser mocks where the provider is not under test. Real parser tests use synthetic workbooks.

Changing the parser must not require rewriting LangGraph tests or PII policy tests. The provider interface is tested as a contract rather than through implementation-specific internals.

## 52. Performance Test Matrix

Measure a small workbook, several worksheets, the five-sheet boundary, 50-row and 50-column boundaries, a 5,000-character cell, formulas, tables, merged ranges, PII-heavy content, preview generation, combined-text generation, and end-to-end Input Processor latency.

Record results against the broader 5 to 6 second target. Do not add a hard spreadsheet threshold until baseline data exists.

## 53. Implementation Phases

### Phase 1: Contract finalization

1. Finalize `SpreadsheetContent` and nested schemas.
2. Confirm the `NormalizedInput` extension.
3. Confirm warning, limit, and partial-success semantics.
4. Confirm provenance representation.
5. Confirm PII detector and failure policy.

### Phase 2: Architecture and configuration

1. Record the dependency decision.
2. Add centralized spreadsheet settings.
3. Define the parser provider protocol.
4. Define safe error categories.
5. Update GraphState and normalized-input documentation.

### Phase 3: Fixtures and provider

1. Add synthetic workbook fixture helpers.
2. Add valid and invalid workbook fixtures.
3. Implement the provider adapter.
4. Add provider contract tests.
5. Add validation tests.

### Phase 4: Processor

1. Add `.xlsx` routing.
2. Implement workbook validation.
3. Implement bounded visible-sheet extraction.
4. Implement formulas and cached values.
5. Implement merged ranges and tables.
6. Implement truncation and PII masking.
7. Implement normalization, preview, and combined text.

### Phase 5: Integration and verification

1. Extend `NormalizedInput` construction.
2. Update GraphState serialization and intent context.
3. Preserve upload/source provenance downstream.
4. Add API and mixed-modality coverage.
5. Run unit, integration, graph, API, privacy, failure, and regression tests.
6. Measure representative performance and update documentation.

## 54. Required Documentation Updates

Update the requirements document, decision log, overall architecture, Input Processor architecture, guardrails, testing strategy, GraphState/state documentation, normalized-input contract, project status, and dependency documentation.

Each document must distinguish proposed, confirmed, and implemented behavior. No document should claim spreadsheet support is implemented before code and tests are complete.

## 55. Open Decisions Before Coding

Finalize:

- Exact `SpreadsheetContent` Pydantic schema.
- Exact field name and placement in `NormalizedInput`.
- Whether row/column overflow is partial success or hard failure.
- Preview sample size N.
- Date and number serialization.
- Error codes and warning shape.
- PII detector and detector-failure behavior.
- Provenance fields for uploaded content.
- Provider interface details.
- Protected-workbook detection behavior.
- Observability provider and redaction rules.
- Upload-aware Context Builder behavior.
- API/frontend acceptance timing.

Record these decisions before implementation begins.

## 56. Definition of Done

Spreadsheet integration is ready for acceptance when:

- `.xlsx` routing, signature validation, and workbook validation are implemented.
- Five-sheet, 50-row, 50-column, and 5,000-character limits are enforced.
- Visible worksheets are processed in order and hidden content is excluded.
- Empty sheets are represented.
- Formulas and cached values are preserved separately.
- Merged ranges and Tables are preserved.
- Cell-level PII masking is implemented.
- Instruction-like content remains untrusted data.
- Protected and macro-enabled workbooks fail safely.
- Preview and combined text are bounded and deterministic.
- Structured spreadsheet content enters `NormalizedInput`.
- GraphState receives no raw workbook data.
- Cleanup works on success and failure paths.
- Mixed-modality behavior works.
- Provider, processor, graph, API, privacy, and regression tests pass.
- Performance is measured and required documentation is updated.

## 57. Summary

Excel is added as a structured modality inside the existing Input Processor. `processors.py` remains the router and orchestrator; the spreadsheet processor validates and extracts bounded visible `.xlsx` content.

The normalized contract preserves worksheet, cell, formula, cached-value, merged, and table structure without exposing `openpyxl`. `combined_text` receives a deterministic projection for existing text-oriented components, while PII is masked before normalized output.

Uploaded spreadsheets remain request-scoped and do not become global knowledge. GraphState receives serializable normalized content only, the parser remains replaceable, and the implementation plan should proceed through contract finalization, configuration, fixtures, provider boundaries, validation, extraction, normalization, integration, and verification.
