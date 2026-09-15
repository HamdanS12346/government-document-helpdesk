# Input Processor Dataset Creation Plan

## 1. Objective

Create an evaluation dataset for the Input Processor that verifies
whether the system correctly:

1.  Identifies the modality of the user input.
2.  Determines whether the input is valid and fits the expected input
    structure.

The dataset will be used by the Input Processor evaluator to compare the
application's actual output against manually defined expected results.

------------------------------------------------------------------------

## 2. Dataset Location

Create the dataset at:

``` text
evaluation/
└── datasets/
    └── input_processor/
        └── cases.jsonl
```

Use a single `cases.jsonl` file.

Each test case will be one JSON object on one line. Do not create a
separate JSON file for each case.

------------------------------------------------------------------------

## 3. Dataset Case Structure

Each case should contain:

-   `id` --- unique test-case identifier.
-   `input` --- the input supplied to the Input Processor.
-   `expected.valid` --- whether the input should be accepted as valid.
-   `expected.modality` --- the modality or combination of modalities
    expected.

Example:

``` json
{
  "id": "IP-001",
  "input": {
    "text": "What documents are required to apply for a passport?",
    "attachments": []
  },
  "expected": {
    "valid": true,
    "modality": ["text"]
  }
}
```

For a text + PDF input:

``` json
{
  "id": "IP-002",
  "input": {
    "text": "What documents are required?",
    "attachments": ["sample_passport.pdf"]
  },
  "expected": {
    "valid": true,
    "modality": ["text", "pdf"]
  }
}
```

The exact field names should match the Input Processor's actual
input/output schema once finalized.

------------------------------------------------------------------------

## 4. Dataset Categories

Build the dataset as a test matrix rather than as random examples.

### 4.1 Text Inputs

Create approximately 5 cases.

Examples should include:

-   Simple text question.
-   Short text.
-   Long text.
-   Government-document-related text.
-   Natural-language text with different wording.

Expected modality:

``` text
["text"]
```

------------------------------------------------------------------------

### 4.2 Image Inputs

Create approximately 5 cases.

Examples should include:

-   A government document image.
-   A screenshot.
-   An image containing text.
-   Different common image formats if supported.
-   An image with a short accompanying description if applicable.

Expected modality:

``` text
["image"]
```

------------------------------------------------------------------------

### 4.3 PDF Inputs

Create approximately 5 cases.

Examples should include:

-   A valid government document PDF.
-   A text-based PDF.
-   A multi-page PDF.
-   A PDF containing relevant document information.
-   Different supported PDF characteristics.

Expected modality:

``` text
["pdf"]
```

------------------------------------------------------------------------

### 4.4 Text + Image

Create approximately 5 cases.

Examples:

-   Text question + image.
-   Text describing what to look for in the image.
-   Text asking a question about the attached image.
-   Short text + image.
-   Longer text + image.

Expected modality:

``` text
["text", "image"]
```

------------------------------------------------------------------------

### 4.5 Text + PDF

Create approximately 5 cases.

Examples:

-   Question + PDF.
-   Text asking for information from the PDF.
-   Text providing context for the PDF.
-   Different question styles with the same PDF.
-   Multiple supported PDF characteristics.

Expected modality:

``` text
["text", "pdf"]
```

------------------------------------------------------------------------

### 4.6 Image + PDF

Create approximately 3 cases.

Examples:

-   Image + PDF containing related information.
-   Image + PDF with a short or no text prompt.
-   Image + PDF representing different document sources.

Expected modality:

``` text
["image", "pdf"]
```

------------------------------------------------------------------------

### 4.7 Text + Image + PDF

Create approximately 3 cases.

Examples:

-   Text question + image + PDF.
-   Text context + image + PDF.
-   A complete multimodal request involving all three input types.

Expected modality:

``` text
["text", "image", "pdf"]
```

------------------------------------------------------------------------

## 5. Invalid and Edge Cases

Create approximately 8 cases.

These cases are important because the Input Processor should not only
classify normal inputs.

Include cases such as:

1.  Empty input.
2.  Empty text with no attachments.
3.  Unsupported file type.
4.  Corrupt PDF.
5.  Invalid or unreadable attachment.
6.  File exceeding the supported size.
7.  PDF exceeding the supported page limit.
8.  Too many attachments.
9.  Missing attachment metadata, if applicable.
10. Other malformed input structures defined by the application's
    schema.

For invalid cases:

``` json
{
  "id": "IP-EDGE-001",
  "input": {
    "text": "",
    "attachments": []
  },
  "expected": {
    "valid": false,
    "modality": []
  }
}
```

The exact expected result for each edge case must follow the Input
Processor's actual validation rules.

------------------------------------------------------------------------

## 6. Recommended Initial Dataset Size

Start with approximately 38--41 cases:

  Category                Cases
  -------------------- --------
  Text                        5
  Image                       5
  PDF                         5
  Text + Image                5
  Text + PDF                  5
  Image + PDF                 3
  Text + Image + PDF          3
  Edge / Invalid              8
  **Total**              **39**

The dataset can be expanded later based on failures observed during
evaluation.

------------------------------------------------------------------------

## 7. Ground Truth Rules

Ground truth must be defined manually.

For each case:

1.  Determine which modalities are actually present.
2.  Determine whether the input satisfies the application's input
    requirements.
3.  Record the expected modality.
4.  Record whether the input is valid.

Do not infer ground truth from the Input Processor's own prediction.

The purpose of the evaluation is to compare:

``` text
Expected Result
       ↓
     vs.
       ↓
Actual Input Processor Result
```

------------------------------------------------------------------------

## 8. Case Creation Process

### Step 1 --- Confirm the Input Schema

Before creating the final dataset, document the exact input structure
accepted by the Input Processor.

For example:

``` text
input
├── text
└── attachments
    ├── file name
    ├── file type
    └── other metadata
```

Use the application's actual schema rather than assuming the example
structure above is final.

### Step 2 --- Define Supported Modalities

Confirm the modalities supported by the application:

-   Text
-   Image
-   PDF

Also confirm which combinations are valid.

### Step 3 --- Define Validation Rules

Document the rules for:

-   Empty input.
-   Unsupported files.
-   Corrupt files.
-   File size.
-   Page limits.
-   Attachment limits.
-   Missing metadata.
-   Other schema constraints.

### Step 4 --- Create the Test Matrix

Create cases across every modality and supported combination.

### Step 5 --- Add Edge Cases

Add invalid and boundary cases specifically designed to test validation
behavior.

### Step 6 --- Review Ground Truth

Manually verify every case before using the dataset for evaluation.

### Step 7 --- Save as JSONL

Store all cases in:

``` text
evaluation/datasets/input_processor/cases.jsonl
```

------------------------------------------------------------------------

## 9. Quality Checks

Before running the evaluator, verify:

-   Every case has a unique ID.
-   Every case contains the required input fields.
-   Every case has an expected result.
-   Modality labels use one consistent naming convention.
-   Invalid cases have clearly defined expected behavior.
-   All referenced test files actually exist and can be accessed by the
    evaluation environment.
-   Cases cover every supported modality combination.
-   Cases contain both normal and edge inputs.
-   Ground truth was defined independently of the Input Processor's
    output.

------------------------------------------------------------------------

## 10. Evaluation Metrics

The dataset should support at least two separate measurements:

### Modality Classification Accuracy

Measures whether the Input Processor correctly identifies:

``` text
text
image
pdf
text + image
text + pdf
image + pdf
text + image + pdf
```

### Input Validation Accuracy

Measures whether the Input Processor correctly determines:

``` text
valid
invalid
```

These should be reported separately so that a modality-classification
problem is not confused with an input-validation problem.

------------------------------------------------------------------------

## 11. Expansion Strategy

Do not try to create hundreds of cases immediately.

Start with the initial \~39 cases, run the evaluation, and inspect
failures.

Add more cases where the Input Processor struggles, especially:

-   Similar-looking inputs.
-   Unusual file combinations.
-   Boundary conditions.
-   Unsupported files.
-   Malformed inputs.
-   Inputs that contain little or no text.
-   Multimodal combinations.

The dataset should evolve based on real failure cases while retaining
the original cases as a regression set.

------------------------------------------------------------------------

## 12. Final Deliverable

The initial deliverable is:

``` text
evaluation/
└── datasets/
    └── input_processor/
        └── cases.jsonl
```

The file should contain approximately 39 manually reviewed test cases
covering normal, multimodal, invalid, and edge-case inputs.

The dataset should be independent of the evaluator implementation so
that the same ground truth can be reused whenever the Input Processor is
changed.
