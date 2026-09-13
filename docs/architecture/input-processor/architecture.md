# Input Processor Architecture
# 1. Purpose
The Input Processor is the multimodal input-processing subsystem of the Government Document Helpdesk Chatbot.
Its responsibility is to accept a single user request containing optional text and zero or more uploaded attachments, safely process the supported modalities, normalize the usable content, and return a `NormalizedInput` object plus structured processing status/errors.
The Input Processor is intentionally isolated from:
* LangGraph workflow logic
* Intent classification
* RAG/retrieval
* Response generation
* Conversation memory
* Frontend/API implementation
* Long-term document storage
The subsystem must expose a stable contract so that other team members can integrate with it without depending on its internal implementation.
The project's architecture requires modular ownership boundaries and explicit contracts so that engineers can work independently and integrate later. The Input Processor therefore owns the complete lifecycle of raw user uploads from receipt through transient processing and normalization, but raw uploaded documents must not persist after processing.
# 2. Scope
## 2.1 Supported input modalities
The MVP Input Processor supports:
* Text
* PNG images
* JPEG images
* JPG images
* PDF documents
A request may contain:
* text only
* one image
* multiple images
* one PDF
* multiple PDFs
* text + images
* text + PDFs
* text + images + PDFs
* attachments without user text
Unsupported file types are rejected before modality-specific processing.
# 3. Ownership Boundary
The Input Processor owns:
1. Input inspection
2. Modality identification
3. Attachment validation
4. File-signature verification
5. File-size validation
6. PDF page-count validation
7. Dispatch to modality-specific processors
8. Image OCR processing
9. PDF text/scanned/mixed processing
10. PII detection/masking within extracted content
11. Input-processing safety checks
12. Deterministic preview construction
13. Collection of successful processing results
14. Construction of `NormalizedInput`
15. Structured safe errors
16. Partial-success handling
17. Cleanup/disposal of raw attachment data
The Input Processor does **not** own:
* Intent classification
* RAG
* Retrieval
* LLM generation
* Final answer safety
* Long-term memory
* Conversation persistence
* Authoritative government knowledge
* Citation generation for government knowledge
* API/frontend behavior
The subsystem should therefore be replaceable without requiring downstream components to understand its internal processing pipeline.
# 4. High-Level Architecture
The Input Processor receives optional `user_query` text and transient attachment bytes, validates them, routes supported images/PDFs to modality processors, applies PII/safety handling to extracted text, builds deterministic previews, and returns normalized content for LangGraph.
Canonical flow:
```text
User Request -> Input Processor -> guardrails -> image/pdf processors
-> OCR/PDF extraction -> PII masking/safety -> NormalizedInput
-> GraphState.normalized_input -> downstream workflow
```
Raw uploaded bytes exist only during request processing. They must not become persistent application state, long-term memory, global knowledge, vector-store content, logs, or traces.
# 5. Internal Folder Responsibility
The planned subsystem structure is:
```text
app/
├── graph/
│   └── state.py
│
├── input-processor/
│   ├── processors.py
│   ├── image_processor.py
│   ├── pdf_processor.py
│   ├── schemas.py
│   └── ...
│
├── guardrails/
│   └── input-processor.py
│
└── ...
```
The exact filename/module naming can be adjusted to the repository's Python naming conventions during implementation, but the responsibility boundaries should remain unchanged.
# 6. `processors.py`
## 6.1 Responsibility
`processors.py` is the **orchestrator/router**.
It must not contain modality-specific processing logic.
Its responsibilities are:
```text
inspect input
      ↓
identify modalities
      ↓
validate
      ↓
dispatch
      ↓
collect results
      ↓
construct NormalizedInput
```
It should coordinate the subsystem rather than implement OCR or PDF parsing itself.
## 6.2 What `processors.py` must not do
It must not contain:
* Tesseract implementation
* PDF parsing implementation
* Docling-specific extraction logic
* image preprocessing logic
* PDF page rendering logic
* modality-specific OCR configuration
* modality-specific extraction rules
Those responsibilities belong behind their respective processor/provider boundaries.
# 7. Input Contract
The Input Processor receives an `InputRequest`.
Conceptually:
```text
InputRequest
├── user_query: optional str
└── attachments: list[Attachment]
```
An attachment contains:
```text
Attachment
├── filename
├── media_type
└── content: bytes
```
## 7.1 `user_query`
The user's text is optional.
Examples:
```text
"What does this document mean?"
```
or:
```text
None
```
If there is no user text but attachments are present, the Input Processor still processes the attachments and creates normalized content.
# 8. Attachment Representation
Attachments should cross the Input Processor boundary as transient bytes.
The Input Processor should not depend on:
* filesystem paths
* frontend-specific upload objects
* API-framework-specific file classes
* permanent object-storage references
This keeps the subsystem independent of the eventual API/frontend technology.
The conceptual boundary is:
```text
Caller
  ↓
Attachment
  ├── filename
  ├── media_type
  └── content: bytes
```
The caller owns creation of the request.
The Input Processor owns processing of those bytes.
The raw bytes are discarded after processing is complete.
# 9. Modality Identification
The Input Processor must not trust the declared MIME type alone.
Modality validation should use:
```text
Declared media_type
        +
Actual file signature / file-content inspection
        ↓
Validated modality
```
For example:
```text
image/png  → verify actual PNG signature
image/jpeg → verify actual JPEG signature
application/pdf → verify actual PDF signature
```
A filename such as:
```text
malicious_file.exe.pdf
```
must not be trusted simply because its filename ends with `.pdf`.
A mismatch between declared type and actual file signature must result in a safe rejection.
# 10. Supported Modality Routing
After validation:
```text
PNG
JPEG
JPG
   ↓
image_processor
PDF
   ↓
pdf_processor
```
Text does not require a modality-specific file processor.
The user query is passed into normalization as `user_query`.
# 11. Multiple Attachments
A single request can contain multiple attachments.
Example:
```text
user_query:
"What are these documents?"
attachments:
    image1.jpg
    image2.png
    document1.pdf
    document2.pdf
    document3.pdf
```
Each attachment is independently processed.
For the initial implementation, attachments are processed **sequentially**.
The contract should nevertheless keep each attachment independently processable so that parallel processing can be introduced later without changing the external Input Processor contract.
Current execution model:
```text
attachment 1
    ↓
validate → process → result
attachment 2
    ↓
validate → process → result
attachment 3
    ↓
validate → process → result
```
Parallel processing is not part of the initial implementation.
# 12. Partial Success
One failed attachment must not automatically invalidate successful attachments.
Example:
```text
image1.jpg       → SUCCESS
image2.jpg       → SUCCESS
bad.pdf          → FAILURE
image3.png       → SUCCESS
```
The result should preserve usable normalized content from:
```text
image1
image2
image3
```
while returning a structured safe error for:
```text
bad.pdf
```
This is important because a multimodal request may contain several independent useful documents.
The downstream system must therefore be able to distinguish:
* successful normalized content
* attachment-specific processing failures
* complete processing failure
# 13. NormalizedInput Contract
The existing `NormalizedInput` structure must **not be changed** as part of this Input Processor implementation.
Current contract:
```text
NormalizedInput
├── user_query: str
├── image_content: List[ImageContent]
├── pdf_content: List[PDFContent]
└── combined_text: str
```
`ImageContent`:
```text
ImageContent
├── image_name: str
├── extracted_text: str
└── preview: str
```
`PDFContent`:
```text
PDFContent
├── pdf_name: str
├── extracted_text: str
└── preview: str
```
No additional fields should be introduced merely to support future functionality.
In particular, the Input Processor should not expand the contract with:
* tables
* bounding boxes
* page objects
* layout objects
* coordinates
* section objects
* provenance objects
* OCR confidence objects
unless the project later explicitly changes the contract.
# 14. What Survives Normalization
The normalized result preserves:
### User text
The original user query, when supplied.
### Image content
For every successfully processed image:
* image name
* extracted text
* deterministic preview
### PDF content
For every successfully processed PDF:
* PDF name
* extracted text
* deterministic preview
### Combined text
`combined_text` contains the user query and successfully extracted document content.
Failed attachments must not have error messages inserted into `combined_text`.
# 15. Deterministic Preview
Previews must be deterministic and must not be LLM-generated.
## Image preview
The image preview contains up to the first:
```text
500 characters
```
of the extracted image text.
## PDF preview
The PDF preview uses:
```text
500 characters per page
```
The preview exists primarily as lightweight normalized information for downstream processing such as intent classification.
The preview must not require an LLM call.
# 16. Empty User Query
A request can contain attachments without user text.
Example:
```text
user_query = None
attachments:
    document.jpg
    form.pdf
```
The Input Processor processes the attachments normally.
The resulting normalized content becomes the available input for downstream workflow processing.
The Input Processor does not invent a user question.
# 17. Processing Result
The Input Processor should return a structured result rather than exposing internal exceptions directly.
Conceptually:
```text
InputProcessingResult
├── success
├── normalized_input
└── error
```
The exact schema is implementation detail to be finalized during implementation planning.
The result must support attachment-specific errors so that partial success is possible.
# 18. Complete Failure
If every supplied attachment fails and there is no usable user text/content, the processing result is:
```text
success = false
```
No usable `NormalizedInput` should be treated as successfully processed content.
The system should return a safe, user-understandable error rather than exposing stack traces, dependency errors, internal paths, or implementation details.
# 19. Image Processor
`image_processor.py` owns image-specific processing.
The high-level pipeline is:
```text
Image bytes
     ↓
image validation
     ↓
OCR
     ↓
PII detection/masking
     ↓
security/safety processing
     ↓
deterministic preview
     ↓
ImageContent
```
The Image Processor must not be responsible for routing PDFs or constructing the overall `NormalizedInput`.
# 20. OCR Provider Abstraction
OCR must be behind a replaceable provider interface.
Conceptually:
```text
OCR Provider
     │
     └── current implementation: Tesseract
```
The rest of the Input Processor should depend on the OCR capability rather than directly coupling every component to Tesseract.
This allows the OCR implementation to be replaced later without redesigning:
* `processors.py`
* `image_processor.py`'s public contract
* `pdf_processor.py`
* downstream LangGraph components
Tesseract is the current implementation direction for the Input Processor.
The provider abstraction should remain narrow and focused on OCR/text extraction rather than prematurely becoming a general "Vision Provider".
# 21. Image OCR Behavior
For the MVP, images should undergo an OCR attempt.
The initial flow is:
```text
image
  ↓
OCR
  ↓
extracted text
```
This introduces processing latency, particularly for large or high-resolution images, but correctness and consistent extraction behavior take priority during the initial implementation.
Performance should be measured rather than prematurely optimizing the architecture.
If OCR produces no useful text, that should be represented as a controlled processing outcome rather than an unhandled exception.
Conceptually:
```text
extracted_text = ""
preview = ""
warning:
    "No readable text could be extracted from this image."
```
The exact warning/error schema is to be finalized with the processing result contract.
# 22. Image Readability
The system requirement says uploaded images should be sufficiently readable for reliable extraction.
A measurable image-quality threshold is currently unresolved at project level.
Therefore:
* The Input Processor must handle unreadable images safely.
* OCR failure/no useful text must not result in fabricated content.
* The system must communicate the limitation.
* A specific numerical image-quality threshold remains `TBD`.
Do not invent a resolution or OCR-confidence threshold without a separate project decision.
# 23. PDF Processor
`pdf_processor.py` owns all PDF-specific processing.
`processors.py` only identifies:
```text
PDF
```
and dispatches the attachment.
The PDF Processor determines whether the PDF is:
```text
TEXT
SCANNED
MIXED
```
and chooses the corresponding processing path.
# 24. PDF Processing
The current PDF processing direction uses Docling as the proposed document-processing component.
The conceptual flow is:
```text
PDF bytes
    ↓
PDF inspection
    ↓
classify
 ┌──────┼───────┐
 ↓      ↓       ↓
TEXT  SCANNED  MIXED
 ↓      ↓       ↓
Docling OCR    Docling + OCR
 └──────┴───────┘
          ↓
     extracted text
          ↓
   PII/safety handling
          ↓
    deterministic preview
          ↓
       PDFContent
```
Docling remains a proposed technology at project level; the Input Processor architecture keeps the PDF-processing responsibility modular so the implementation can be replaced if required.
# 25. Text-Based PDF
For a text-based PDF:
```text
PDF
 ↓
PDF inspection
 ↓
text-based
 ↓
Docling extraction
 ↓
extracted text
 ↓
PII/safety processing
 ↓
PDFContent
```
OCR should not be unnecessarily invoked for regions that are already successfully represented as machine-readable text.
# 26. Scanned PDF
For a scanned PDF:
```text
PDF
 ↓
PDF inspection
 ↓
scanned
 ↓
page extraction/rendering
 ↓
OCR provider
 ↓
page-level extracted text
 ↓
combine
 ↓
PII/safety processing
 ↓
PDFContent
```
The OCR provider should process scanned content at page level.
This also supports the deterministic preview rule:
```text
500 characters per page
```
# 27. Mixed PDF
Mixed PDFs are supported.
Example:
```text
Page 1 → machine-readable text
Page 2 → scanned
Page 3 → machine-readable text
Page 4 → scanned
```
The PDF Processor should select the appropriate extraction path for each page/region as required.
Conceptually:
```text
Page 1 → Docling
Page 2 → OCR
Page 3 → Docling
Page 4 → OCR
```
The resulting extracted content is combined into the PDF's normalized text representation.
Mixed PDFs must not be treated as unsupported.
# 28. PDF Page Limit
The current Input Processor design specifies:
```text
Maximum PDF pages = 5
```
This is an Input Processor guardrail and must be checked before PDF processing begins.
However, the existing project decision log currently contains a confirmed project-wide requirement of:
```text
Maximum PDF pages = 10
```
Therefore the 5-page rule must be treated as a **new proposed Input Processor constraint pending decision-log update**, unless the team explicitly confirms that it replaces the existing 10-page decision.
Required change-management action:
```text
CHANGE IMPACT
Changed:
PDF Input Processor page limit: 10 → 5
Direct impact:
Input Processor PDF validation
CLI fixtures
PDF tests
User-facing upload errors
Indirect impact:
Performance expectations
Multimodal evaluation
Requirements/acceptance criteria
Documents to update:
02_DECISION_LOG.md
01_REQUIREMENTS.md
06_MULTIMODAL_INGESTION.md
13_TESTING_STRATEGY.md
Input Processor architecture/guardrails/testing docs
Tests/evaluations affected:
PDF boundary tests
5-page success
6-page rejection
Existing 10-page assumptions
Implementation consequence:
PDF page validation must enforce the confirmed final value.
```
Until this is resolved, implementation should not silently claim that the entire project has changed to 5 pages.
# 29. Guardrail Boundary
The Input Processor has its own guardrail layer under:
```text
guardrails/
└── input-processor.py
```
The purpose of this layer is to enforce safety constraints around uploaded input and extracted content.
The Input Processor guardrail layer must remain separate from:
* final-response guardrails
* RAG safety
* LLM output safety
* application-wide policy decisions
# 30. Guardrail Summary
The detailed rules live in `docs/architecture/input-processor/guardrails.md`. Architecture-level requirements are:
* validate structure, declared media type, actual signature, file size, and PDF page count before expensive processing
* reject unsupported/invalid/oversized inputs before OCR or PDF parsing
* apply PII detection/masking after OCR/PDF extraction
* default PII behavior is mask-and-continue
* treat uploaded document instructions as untrusted content, not executable system/developer instructions
* avoid naive keyword rejection because government forms contain ordinary instructions
* keep broader toxic/harmful-content and final-response safety in later guardrail layers
# 31. Raw Upload Lifecycle
The raw upload lifecycle is:
```text
Receive bytes
     ↓
Validate
     ↓
Process
     ↓
Extract
     ↓
Mask / safety processing
     ↓
Construct NormalizedInput
     ↓
Return result
     ↓
Raw upload disposed
```
Raw uploads must not be:
* persisted after processing
* added to long-term memory
* added to the global knowledge base
* added to the vector store
* written into normal application logs
* included unredacted in observability traces
The project explicitly requires that uploaded user documents not be stored after processing.
# 32. Separation From Knowledge Base
User-uploaded documents are **user-provided content**.
They are not automatically authoritative government knowledge.
Therefore:
```text
Uploaded document
      ↓
Current-request processing
      ↓
NormalizedInput
      ↓
conversation/workflow context
```
and not:
```text
Uploaded document
      ↓
global knowledge base
      ↓
vector database
```
The latter would require a separate explicitly approved ingestion workflow.
# 33. LangGraph State Integration
The Input Processor should integrate into LangGraph through `NormalizedInput`.
The existing shared graph state concept is:
```text
GraphState
├── normalized_input
├── intent_decision
├── documents
├── retrieved_context
├── messages
└── conversation_summary
```
`NormalizedInput` is the Input Processor's handoff to the graph.
# 34. `app/graph/state.py`
`state.py` should be created early, before connecting the entire graph.
The purpose is to establish the shared workflow contract.
It should contain the graph-state definition required by the existing architecture.
The state definition should not contain:
* OCR implementation
* PDF processing logic
* guardrail logic
* API handling
* RAG implementation
* LLM calls
The Input Processor writes:
```text
normalized_input
```
into graph state.
Downstream nodes read it.
# 35. Raw Attachments Must Not Enter Graph State
Raw `Attachment` objects and their bytes should not become LangGraph state.
The intended boundary is:
```text
API / CLI
    ↓
Input Processor
    ↓
NormalizedInput
    ↓
LangGraph State
```
Not:
```text
API / CLI
    ↓
LangGraph State
    ↓
Input Processor
```
This keeps raw sensitive uploads outside the shared workflow state.
It also keeps the graph state lightweight and decoupled from the upload mechanism.
# 36. `InputProcessingResult` and Graph State
`InputProcessingResult` is an Input Processor contract.
It should not automatically become a graph-state contract.
Conceptually:
```text
InputProcessor
      ↓
InputProcessingResult
      ↓
successful normalized_input
      ↓
GraphState.normalized_input
```
This keeps LangGraph independent of the Input Processor's internal execution/error representation.
The graph only needs the normalized content and whatever controlled routing/error behavior is defined at the integration boundary.
# 37. CLI-First Development
The Input Processor should be independently testable through a CLI before frontend/API integration.
The CLI should simulate the eventual external boundary:
```text
CLI
 ↓
InputRequest
 ↓
Input Processor
 ↓
InputProcessingResult
 ↓
safe CLI output
```
The CLI should **not** bypass the orchestrator by directly invoking:
```text
image_processor
pdf_processor
```
Testing the individual processors is useful internally, but end-to-end Input Processor testing must go through the public Input Processor boundary.
# 38. Integration Boundary
Other engineers should only need to understand:
```text
InputRequest
       ↓
InputProcessor
       ↓
InputProcessingResult
```
They should not need to know whether the subsystem internally uses:
* Tesseract
* Docling
* temporary processing buffers
* image preprocessing
* PDF rendering
* OCR configuration
* specific parsing implementation
Those are internal implementation details.
# 39. Internal Replaceability
The architecture should maintain replaceable internal capabilities.
Primary conceptual boundaries:
```text
InputProcessor
     │
     ├── ImageProcessor
     │       └── OCRProvider
     │
     └── PDFProcessor
             ├── PDF extraction capability
             └── OCRProvider
```
The current OCR implementation is Tesseract.
The PDF processing direction is Docling.
Neither should leak into the public integration contract.
# 40. Sequential Processing
Initial execution is sequential.
For N attachments:
```text
for each attachment:
    validate
    process
    collect result
```
This is intentional for the initial implementation because it keeps behavior easy to reason about, debug, test, and observe.
Parallel processing may be evaluated later based on measured latency.
The architecture should not require a contract change if parallel processing is introduced.
# 41. Latency Considerations
The overall MVP has an approximate 5–6 second normal response target.
Input processing contributes directly to that latency.
The major potential latency sources are:
```text
Input validation
     +
image OCR
     +
PDF parsing
     +
PDF OCR
     +
PII detection
```
Scanned PDFs are expected to be more expensive than text-based PDFs.
The Input Processor should therefore expose enough operational information internally for stage-level latency measurement without leaking sensitive document content.
Optimization should be measurement-driven.
Possible future optimizations include:
* OCR preprocessing
* optimized OCR configuration
* avoiding unnecessary repeated extraction
* controlled parallel attachment processing
* caching only where privacy/retention rules permit
These are optimization possibilities, not current architecture decisions.
# 42. Failure Boundaries
The Input Processor should classify controlled failures, including:
```text
Unsupported file
Invalid file signature
File too large
PDF too many pages
OCR failure
PDF extraction failure
Unreadable content
PII processing failure
Safety rejection
Unexpected internal processing failure
```
Errors should be structured, attachment-specific where applicable, safe for user display, understandable, and free of stack traces, internal paths, credentials, and unnecessary sensitive content.
Internally, an attachment can move through:
```text
RECEIVED -> VALIDATING -> VALIDATED -> PROCESSING -> NORMALIZED
RECEIVED -> VALIDATING -> REJECTED
RECEIVED -> VALIDATING -> VALIDATED -> PROCESSING -> FAILED
```
This processing-state model is internal and must not expand `NormalizedInput`.
# 43. Recommended Implementation Order
Implement contract-first:
1. Establish `app/graph/state.py` around `NormalizedInput` and existing workflow fields.
2. Add `InputRequest`, `Attachment`, and `InputProcessingResult` schemas without changing `NormalizedInput`.
3. Define the public Input Processor operation.
4. Establish guardrail interfaces callable by the orchestrator.
5. Implement declared media type plus signature validation.
6. Add an `OCRProvider` abstraction with Tesseract as the current implementation direction.
7. Implement image processing: bytes -> OCR -> PII -> preview -> `ImageContent`.
8. Implement PDF processing: inspect/classify -> text/scanned/mixed extraction -> PII -> preview -> `PDFContent`.
9. Connect orchestration in `processors.py`.
10. Integrate only `NormalizedInput` into `GraphState.normalized_input`.
11. Add a CLI path that exercises the public contract.
12. Add fixture-based tests for processors, guardrails, partial/complete failure, normalized output, state integration, privacy, and cleanup.
# 44. Testing Boundary Summary
Detailed testing rules live in `docs/architecture/input-processor/testing.md`. Architecture-level fixture groups are:
```text
tests/input-processor/fixtures/images/{valid,blurry,unreadable,injection}
tests/input-processor/fixtures/pdf/{text,scanned,mixed,over_page_limit,invalid}
```
Minimum coverage must include text-only, text+image, text+PDF, full multimodal input, valid PNG/JPG/JPEG, multiple images/PDFs, text/scanned/mixed PDFs, page-boundary PDFs, invalid files, OCR/PDF failures, partial success, complete failure, attachments without user text, unsupported extensions, MIME/signature mismatch, PII-containing content, prompt-injection-like content, oversized files, cleanup, and privacy boundaries.
# 45. Privacy Testing
Tests must verify that raw sensitive content does not accidentally cross prohibited boundaries.
At minimum, verify that:
```text
raw upload
    X
GraphState
    X
logs
    X
traces
    X
long-term memory
    X
global knowledge base
```
The exact retention policy for derived extracted text, conversations, logs, traces, and evaluation data remains unresolved at project level.
Therefore the Input Processor should not introduce persistent storage for extracted text.
# 46. Security Boundary
The Input Processor is a security boundary around untrusted uploaded data.
Treat all attachments as untrusted input.
The processing pipeline must assume:
```text
filename can be malicious
MIME type can be incorrect
file contents can be malformed
OCR text can contain adversarial instructions
documents can contain PII
documents can be intentionally crafted to consume resources
```
The processor must validate before expensive processing and must return controlled failures.
# 47. Observability Boundary
The Input Processor eventually needs privacy-preserving telemetry for modality, validation outcome, processing path, duration, OCR outcome, PDF classification, guardrail outcome, failure category, and partial-success state.
Telemetry must not capture raw document content or unredacted PII. The observability platform remains TBD, so this architecture defines what should be observable rather than which platform to use.
# 48. Resource Boundaries
The Input Processor must enforce bounded processing.
Current requirements include:
* file-size limit
* PDF page-count limit
* supported modality limit
The project requirements currently specify uploads below 10 MB and PDFs up to 10 pages; the current Input Processor design proposes 5 pages and therefore requires project decision-log reconciliation as described above.
Resource limits exist to control:
* latency
* memory consumption
* OCR cost
* denial-of-service risk
* privacy exposure duration
# 49. No Premature API Dependency
The Input Processor should be implementable and testable without the eventual frontend or API.
The eventual `/chat` endpoint should become merely another caller of the Input Processor contract.
Conceptually:
```text
CLI ──────────┐
              │
API ──────────┼──→ InputProcessor
              │
Tests ────────┘
```
This allows the Input Processor team member to work independently.
# 50. Team Integration Contract
Other team members must not modify Input Processor internals to integrate with it.
They should depend on the documented public contract.
Likewise, the Input Processor should not reach into:
* RAG internals
* LangGraph node internals
* frontend internals
* API internals
* memory internals
The integration surface is the contract.
This supports the project's requirement that four engineers work independently while producing one coherent system.
# 51. Definition of Done
The Input Processor should be considered integration-ready when:
```text
✓ InputRequest contract exists
✓ Attachment contract exists
✓ Raw attachments are transient bytes
✓ Supported text/image/PDF inputs work
✓ PNG/JPEG/JPG are supported
✓ PDF is supported
✓ Declared media type is validated
✓ Actual file signature is validated
✓ Unsupported files are rejected before processing
✓ File-size validation exists
✓ PDF page-count validation exists
✓ Image processing is isolated
✓ PDF processing is isolated
✓ OCR is behind a provider interface
✓ Tesseract implementation works
✓ Text PDFs are handled
✓ Scanned PDFs are handled
✓ Mixed PDFs are handled
✓ PII is detected and masked
✓ Prompt-injection handling boundary exists
✓ NormalizedInput contract is preserved
✓ combined_text contains successful content only
✓ deterministic previews are generated
✓ partial success works
✓ complete failure produces success=false
✓ structured safe errors exist
✓ raw attachments do not enter GraphState
✓ GraphState contains normalized_input
✓ CLI can exercise the public contract
✓ fixture-based tests exist
✓ privacy tests exist
✓ failure tests exist
✓ integration tests exist
✓ raw upload cleanup is verified
✓ downstream components only depend on the public contract
```
# 52. Explicit Non-Goals
The Input Processor does not currently attempt to:
* answer user questions
* retrieve government knowledge
* generate final responses
* perform RAG
* select authoritative government sources
* generate citations for knowledge-base facts
* maintain long-term memory
* persist user documents
* perform final response safety checks
* replace the global guardrail architecture
* implement the frontend
* implement the final API
* implement LangGraph routing beyond the required state handoff
* perform advanced document-layout representation beyond the current normalized contract
# 53. Open/TBD Items
The following remain unresolved or require separate documentation/decision work:
1. Measurable image-quality acceptance threshold.
2. Exact OCR quality threshold.
3. Detailed prompt-injection detection strategy.
4. Exact PII categories and masking rules.
5. Exact safe-error schema.
6. Exact processing-status schema.
7. Exact Input Processor public method/interface naming.
8. Detailed Docling configuration.
9. Detailed Tesseract configuration.
10. Performance thresholds by modality.
11. Retention policy for derived extracted text.
12. Observability platform.
13. API framework.
14. Final PDF page-limit project decision: current Input Processor proposal is 5; existing confirmed project decision is 10.
15. Whether any derived normalized content may persist beyond the current request.
Unresolved project decisions must remain explicitly marked rather than silently finalized.
# 54. Documentation Responsibilities
This document defines component boundaries, data flow, state integration, processing responsibilities, contracts, lifecycle, failure boundaries, implementation order, and integration rules.
Companion documents:
* `docs/architecture/input-processor/guardrails.md` defines detailed security/safety behavior.
* `docs/architecture/input-processor/testing.md` defines fixtures, unit/integration/CLI/failure/privacy/regression/performance tests, acceptance criteria, and verification strategy.
# 55. Final Architecture Summary
The key architectural principle is:
> **Raw multimodal input is owned temporarily by the Input Processor; normalized content is the only contract that leaves the subsystem.**
This allows the Input Processor to evolve internally while the rest of the team integrates against a stable boundary.
