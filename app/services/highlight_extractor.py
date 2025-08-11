import re
from typing import List, Dict, Tuple

# (dimension, regex, why)
BIAS_PATTERNS: List[Tuple[str, str, str]] = [
    # framing
    ("framing_choices", r"\bcritics (?:say|argue|claim)\b", "Uses the 'critics say' construction."),
    ("framing_choices", r"\b(allegedly|reportedly|is said to)\b", "Distance / hedging phrasing."),
    ("framing_choices", r"\b(dubbed|branded|labeled)\b", "Loaded labeling indicates framing."),
    # emotional tone
    ("emotional_tone", r"\b(shocking|outrage|furious|slammed|disgrace|scandal)\b", "Loaded / emotional adjective."),
    ("emotional_tone", r"\b(spiral(?:ling)? out of control|in chaos|in turmoil)\b", "Catastrophizing language."),
    # source transparency
    ("source_transparency", r"\banonymous sources?\b", "Opaque attribution to anonymous sources."),
    ("source_transparency", r"\baccording to sources\b", "Vague attribution ('sources')."),
    ("source_transparency", r"\bpeople familiar with the matter\b", "Non-specific sourcing."),
    # ideology
    ("ideological_stance", r"\b(leftwing|rightwing|far[- ]?right|far[- ]?left)\b", "Explicit ideological labeling."),
]

def extract_highlights(text: str) -> List[Dict]:
    out: List[Dict] = []
    if not text:
        return out
    for dim, rx, why in BIAS_PATTERNS:
        for m in re.finditer(rx, text, flags=re.I):
            start, end = m.span()
            out.append({
                "dimension": dim,
                "data": {
                    "text": text[start:end],
                    "start": start,
                    "end": end,
                    "reason": why,
                    "confidence": 0.8,
                }
            })
    return out
