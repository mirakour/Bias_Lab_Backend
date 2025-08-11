from __future__ import annotations
import json, re
from typing import Dict, Any, List, Tuple

from app.utils.config import OPENAI_API_KEY, ANTHROPIC_API_KEY

# --- Optional clients (loaded lazily so missing keys don't crash import) ---
_openai_client = None
_anthropic_client = None

def _get_openai():
    global _openai_client
    if _openai_client is None and OPENAI_API_KEY:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None and ANTHROPIC_API_KEY:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client

BIAS_DIMENSIONS = [
    "ideological_stance",
    "factual_grounding",
    "framing_choices",
    "emotional_tone",
    "source_transparency",
]

SYSTEM_INSTRUCTIONS = (
    "You are Bias Lab, an expert media-bias analyst. "
    "Given article text, output strict JSON with: "
    "{scores:{dimension:0-100}, highlights:[{dimension,text,start,end,reason,confidence}]}. "
    "Scores: higher is ‘more of the thing’ (e.g., higher emotional_tone = more emotionally loaded). "
    "Use short, defensible highlights; no extra commentary."
)

USER_TEMPLATE = """Article text:
Return ONLY JSON:
{{
  "scores": {{
    "ideological_stance": <0-100>,
    "factual_grounding": <0-100>,
    "framing_choices": <0-100>,
    "emotional_tone": <0-100>,
    "source_transparency": <0-100>
  }},
  "highlights": [
    {{"dimension":"framing_choices","text":"...", "start":12, "end":24, "reason":"...", "confidence":0.72}}
  ]
}}
"""

def _coerce_json(s: str) -> Dict[str, Any]:
    # try plain json first
    try:
        return json.loads(s)
    except Exception:
        pass
    # try to extract the first {...} block
    m = re.search(r"\{.*\}", s, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("LLM did not return valid JSON")

def _rule_based(text: str) -> Dict[str, Any]:
    # Tiny heuristic fallback so we always return *something*
    lower = text.lower()
    emotional = sum(lower.count(w) for w in ["outrage", "shocking", "furious", "disaster"])
    vague = sum(lower.count(p) for p in ["critics say", "some say", "sources say"])
    stance = 50
    factual = max(20, 80 - vague * 10)
    framing = min(90, 40 + vague * 15)
    emotion = min(95, 30 + emotional * 20)
    source = max(20, 70 - vague * 10)

    highlights = []
    for phrase in ["critics say", "some say", "sources say"]:
        i = lower.find(phrase)
        if i != -1:
            highlights.append({
                "dimension": "framing_choices",
                "text": text[i:i+len(phrase)],
                "start": i,
                "end": i+len(phrase),
                "reason": "vague attribution",
                "confidence": 0.6,
            })

    return {
        "scores": {
            "ideological_stance": stance,
            "factual_grounding": factual,
            "framing_choices": framing,
            "emotional_tone": emotion,
            "source_transparency": source,
        },
        "highlights": highlights[:3],
    }

def llm_score(text: str) -> Dict[str, Any]:
    """Try OpenAI → Anthropic → rules. Always returns dict with 'scores' and 'highlights'."""
    snippet = text[:8000]  # keep prompt smaller/cheaper

    # 1) OpenAI (gpt-4o-mini is fast/cheap/good)
    try:
        oai = _get_openai()
        if oai:
            msg = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system", "content": SYSTEM_INSTRUCTIONS},
                    {"role":"user", "content": USER_TEMPLATE.format(snippet=snippet)}
                ],
                temperature=0.2,
            )
            out = msg.choices[0].message.content
            data = _coerce_json(out)
            _validate_dims(data)
            return data
    except Exception:
        pass

    # 2) Anthropic fallback
    try:
        claude = _get_anthropic()
        if claude:
            msg = claude.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=1200,
                temperature=0.2,
                system=SYSTEM_INSTRUCTIONS,
                messages=[
                    {"role":"user", "content": USER_TEMPLATE.format(snippet=snippet)}
                ]
            )
            # anthropic returns content as blocks
            out = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
            data = _coerce_json(out)
            _validate_dims(data)
            return data
    except Exception:
        pass

    # 3) Rules
    return _rule_based(text)

def llm_summary(text: str) -> str:
    try:
        from app.utils.config import OPENAI_API_KEY
        if OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = (
                "You are a neutral news analyst. Write a cohesive single paragraph of 10–12 sentences "
                "summarizing the article. Be factual and concise. Avoid opinionated language. "
                "Do not add facts that aren’t in the text. No bullets; one paragraph."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text[:12000]},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
    except Exception:
        pass

    import re
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sents[:12])[:2500]

def _validate_dims(data: Dict[str, Any]) -> None:
    scores = data.get("scores", {})
    for d in BIAS_DIMENSIONS:
        v = scores.get(d)
        if not isinstance(v, (int, float)):
            raise ValueError("missing/invalid score")
    if "highlights" not in data or not isinstance(data["highlights"], list):
        data["highlights"] = []

def extract_claims(text: str) -> List[Dict[str, Any]]:
    """
    Returns a small set of atomic claims:
    [{ "text": str, "rationale": str, "confidence": float }]
    """
    try:
        from app.utils.config import OPENAI_API_KEY
        if OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            system = (
                "You extract atomic, checkable claims from news articles. "
                "Return STRICT JSON with key 'claims': "
                "[{text:..., rationale:..., confidence:0-1}]. 3–8 items, short and factual."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system","content":system},
                    {"role":"user","content":text[:8000]},
                ],
                temperature=0.2,
            )
            import json, re
            raw = resp.choices[0].message.content
            block = re.search(r"\{.*\}", raw, flags=re.S)
            data = json.loads(block.group(0)) if block else json.loads(raw)
            claims = data.get("claims", [])
            return [
                {
                    "text": c.get("text","").strip(),
                    "rationale": c.get("rationale","").strip(),
                    "confidence": float(c.get("confidence", 0.5))
                }
                for c in claims if c.get("text")
            ][:8]
    except Exception:
        pass

    # crude fallback: pick a few strong sentences as "claims"
    import re
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    pick = [s for s in sents if len(s) > 60][:4]
    return [{"text": s, "rationale": "salient sentence", "confidence": 0.4} for s in pick]