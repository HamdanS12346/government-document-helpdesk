# Normalized Input

## Overview

`NormalizedInput` is the standardized representation of everything provided by the user at the start of the workflow.

The user can provide:

* Text query
* One or more images
* One or more PDFs
* A combination of the above

The Input Processor is responsible for processing these inputs and producing a single `NormalizedInput` object.

The purpose of normalization is to give downstream nodes a consistent structure regardless of how the user provided the input.

Downstream nodes should not need to handle raw file types or modality-specific input handling.

---

## Schema

```text
NormalizedInput
├── user_query: str
├── image_content: List[ImageContent]
├── pdf_content: List[PDFContent]
└── combined_text: str
```

### `user_query`

```text
user_query: str
```

The text entered directly by the user.

This represents the user's actual question or request.

Example:

```text
"Can I use this document as proof of address?"
```

---

### `image_content`

```text
image_content: List[ImageContent]
```

A list containing the processed content of all images attached by the user.

If no images are provided:

```text
image_content = []
```

Each image is represented by an `ImageContent` object.

### `ImageContent`

```text
ImageContent
├── image_name: str
├── extracted_text: str
└── preview: str
```

* `image_name`: Name of the uploaded image.
* `extracted_text`: Text extracted/processed from the image.
* `preview`: A limited representation of the extracted content used to give downstream classification a quick understanding of the attachment without passing the entire content.

The preview is intended to be lightweight and should not be an LLM-generated summary.

---

### `pdf_content`

```text
pdf_content: List[PDFContent]
```

A list containing the processed content of all PDFs attached by the user.

If no PDFs are provided:

```text
pdf_content = []
```

Each PDF is represented by a `PDFContent` object.

### `PDFContent`

```text
PDFContent
├── pdf_name: str
├── extracted_text: str
└── preview: str
```

* `pdf_name`: Name of the uploaded PDF.
* `extracted_text`: Text extracted/processed from the PDF.
* `preview`: A limited representation of the extracted content used to give downstream classification a quick understanding of the attachment without passing the entire content.

The preview is intended to be lightweight and should not be an LLM-generated summary.

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

This provides a convenient textual representation for downstream components that need access to the normalized textual information together.

`combined_text` should not replace the structured `image_content` and `pdf_content` fields. Those fields remain available when modality-specific information is required.

---

# Examples

## 1. Text Only

User:

```text
"What documents are required for PAN application?"
```

Normalized input:

```text
NormalizedInput(
    user_query="What documents are required for PAN application?",

    image_content=[],

    pdf_content=[],

    combined_text="""
    User Query:
    What documents are required for PAN application?
    """
)
```

---

## 2. User Query + One Image

User:

```text
"Can I use this as proof of address?"
```

Attachment:

```text
address_certificate.jpg
```

Normalized input:

```text
NormalizedInput(
    user_query="Can I use this as proof of address?",

    image_content=[
        ImageContent(
            image_name="address_certificate.jpg",
            extracted_text="Certificate of Residence\nName: Rahul Sharma\nAddress: ...",
            preview="Certificate of Residence\nName: Rahul Sharma\nAddress: ..."
        )
    ],

    pdf_content=[],

    combined_text="""
    User Query:
    Can I use this as proof of address?

    Attached Image:
    address_certificate.jpg

    Content:
    Certificate of Residence
    Name: Rahul Sharma
    Address: ...
    """
)
```

---

## 3. User Query + Multiple Images

User:

```text
"What are these documents?"
```

Attachments:

```text
image1.jpg
image2.jpg
image3.jpg
```

Normalized input:

```text
NormalizedInput(
    user_query="What are these documents?",

    image_content=[
        ImageContent(
            image_name="image1.jpg",
            extracted_text="...",
            preview="..."
        ),
        ImageContent(
            image_name="image2.jpg",
            extracted_text="...",
            preview="..."
        ),
        ImageContent(
            image_name="image3.jpg",
            extracted_text="...",
            preview="..."
        )
    ],

    pdf_content=[],

    combined_text="..."
)
```

Each attachment is represented independently in the list.

---

## 4. User Query + PDF

User:

```text
"What is the procedure mentioned in this document?"
```

Attachment:

```text
pan_procedure.pdf
```

Normalized input:

```text
NormalizedInput(
    user_query="What is the procedure mentioned in this document?",

    image_content=[],

    pdf_content=[
        PDFContent(
            pdf_name="pan_procedure.pdf",
            extracted_text="...",
            preview="..."
        )
    ],

    combined_text="..."
)
```

---

## 5. Mixed Input

User:

```text
"Can these documents be used for the application?"
```

Attachments:

```text
identity_proof.jpg
address_proof.jpg
application_guidelines.pdf
```

Normalized input:

```text
NormalizedInput(
    user_query="Can these documents be used for the application?",

    image_content=[
        ImageContent(
            image_name="identity_proof.jpg",
            extracted_text="...",
            preview="..."
        ),
        ImageContent(
            image_name="address_proof.jpg",
            extracted_text="...",
            preview="..."
        )
    ],

    pdf_content=[
        PDFContent(
            pdf_name="application_guidelines.pdf",
            extracted_text="...",
            preview="..."
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
      ↓
Processing / Extraction
      ↓
NormalizedInput
```

After this point, downstream nodes work with the normalized structure rather than dealing directly with raw text, images, or PDFs.

The detailed implementation of text extraction, OCR, PDF parsing, preview generation, and other modality-specific processing belongs inside the Input Processor and its processors. The contract above defines only what the Input Processor exposes to the rest of the system.
