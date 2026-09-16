"""Thread title generator for conversation history."""

import re
from typing import Optional


def generate_thread_title(query: Optional[str] = None) -> str:
    """Generate a clean, compact title (3-7 words) from the user's initial query."""
    if not query or not query.strip():
        return "New Consultation"

    # Clean whitespace and unwanted characters
    cleaned = re.sub(r"\s+", " ", query.strip())
    # Strip common leading question prefixes
    cleaned = re.sub(r"^(can you tell me|how do i|how to|what is the process for|what are the requirements for|tell me about|what is|where can i)\s+", "", cleaned, flags=re.IGNORECASE)
    
    words = cleaned.split(" ")
    if len(words) > 7:
        title = " ".join(words[:7]).strip(",.-?") + "..."
    else:
        title = " ".join(words).strip(",.-?")

    # Capitalize title
    title = title[:1].upper() + title[1:]
    return title or "New Consultation"
