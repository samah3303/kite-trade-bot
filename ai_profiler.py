"""
KiteAlerts V6.0 — AI Context Profiler
Groq Llama 3.3 — Risk Manager persona.
Returns 3 punchy bullet points. Does NOT block trades.
"""

import os
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()


def profile_market(market_snapshot, signal_data):
    """
    AI context profiler. Reads the same JSON snapshot as the math profiler.

    Args:
        market_snapshot: dict with price, RSI, ATR, ADX, VWAP distance, etc.
        signal_data: dict with direction, entry, SL, target, engine

    Returns:
        dict: {"tag": "...", "bullets": ["...", "...", "..."]}
    """
    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        logging.warning("[AI] GROQ_API_KEY not set. Skipping AI profiler.")
        return _fallback("AI key not configured")

    try:
        snapshot_json = json.dumps(market_snapshot, indent=2, default=str)
        signal_json = json.dumps(signal_data, indent=2, default=str)

        prompt = f"""You are an institutional risk manager reviewing a real-time trade alert.

Your job is to provide CONTEXT, not a decision. The trader makes the final call.

Analyze the market snapshot and the proposed signal. Return EXACTLY this JSON:
{{
  "tag": "<one-line market characterization, max 6 words>",
  "bullets": [
    "<WHY the market is moving this way — max 15 words>",
    "<WHO is trapped on the wrong side — max 15 words>",
    "<Does broader context support the signal? — max 15 words>"
  ]
}}

RULES:
- Be specific and punchy. No filler words.
- Reference actual numbers from the snapshot (RSI, ADX, VWAP distance).
- Do NOT say "ACCEPT" or "RESTRICT". You are NOT a gatekeeper.
- Do NOT suggest changes to entry/SL/target.

Market Snapshot:
{snapshot_json}

Proposed Signal:
{signal_json}"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {groq_api_key}",
        }

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an institutional risk manager. Return ONLY valid JSON. No markdown, no explanation.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.15,
            "max_tokens": 250,
            "response_format": {"type": "json_object"},
        }

        # Retry with backoff
        for attempt in range(3):
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=8,
                )

                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"]
                    text = text.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(text)

                    tag = str(parsed.get("tag", "AI Profile"))[:50]
                    bullets = parsed.get("bullets", [])
                    if not isinstance(bullets, list):
                        bullets = [str(bullets)]
                    bullets = [str(b)[:80] for b in bullets[:3]]

                    return {"tag": tag, "bullets": bullets}

                elif resp.status_code == 429:
                    logging.warning(f"[AI] Rate limited. Retry {attempt + 1}/3...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logging.error(f"[AI] Groq {resp.status_code}: {resp.text[:200]}")
                    return _fallback(f"API error {resp.status_code}")

            except requests.exceptions.Timeout:
                logging.warning(f"[AI] Timeout. Retry {attempt + 1}/3...")
                time.sleep(1)
                continue
            except Exception as e:
                logging.error(f"[AI] Request error: {e}")
                return _fallback(str(e))

        return _fallback("Max retries exceeded")

    except Exception as e:
        logging.error(f"[AI] Profiler error: {e}")
        return _fallback(str(e))


def _fallback(reason="Unknown"):
    """Fail-open fallback. AI failure must never block the alert."""
    return {
        "tag": "AI Unavailable",
        "bullets": [f"Profiler unavailable: {reason}"],
    }
