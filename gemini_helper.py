import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Using the standard endpoint for Gemini 1.5 Flash (latest stable fast model) or 2.0 if available
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

class GeminiHelper:
    def __init__(self):
        self.enabled = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")
        if not self.enabled:
            print("[WARN] GEMINI_API_KEY missing or invalid in .env")

    def analyze_market_sentiment(self, instrument, trend, rsi, atr, pattern, price=0):
        """
        Generates a detailed trade analysis via REST API returning structured JSON.
        """
        if not self.enabled:
            return None

        try:
            prompt = f"""
            You are a rigorous High-Frequency Trading Risk Manager. 
            Analyze this trade setup for {instrument} and output strictly VALID JSON.
            
            Technical Data:
            - Trend: {trend}
            - Pattern: {pattern}
            - RSI: {rsi:.1f} (0-100)
            - ATR: {atr:.2f}
            - Entry Price: {price}
            
            Evaluate the setup's quality based on the trend alignment and indicator confluence.
            
            Output JSON format:
            {{
                "confidence_score": (int 1-10),
                "risk_level": "Low" | "Medium" | "High",
                "action": "Proceed" | "Caution" | "Skip",
                "insight": "Concise analysis (max 20 words)"
            }}
            """

            import time
            max_retries = 3
            base_delay = 2

            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 200,
                    "responseMimeType": "application/json"
                }
            }
            
            headers = {"Content-Type": "application/json"}
            # Revert to 2.0-flash (was working previously)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=10)
                    
                    if response.status_code == 200:
                        result = response.json()
                        text = result['candidates'][0]['content']['parts'][0]['text']
                        text = text.replace('```json', '').replace('```', '').strip()
                        return json.loads(text)
                        
                    elif response.status_code == 429:
                        print(f"[QUOTA] Gemini 429 (Quota). Retrying in {base_delay}s...")
                        time.sleep(base_delay)
                        base_delay *= 2 # Exponential backoff
                        continue
                    else:
                        print(f"[ERROR] Gemini API Error {response.status_code}: {response.text[:200]}")
                        return None
                except Exception as req_err:
                     print(f"[ERROR] Gemini Req Error: {req_err}")
                     if attempt < max_retries - 1: time.sleep(base_delay); continue
                     return None
            
            return None

        except Exception as e:
            print(f"⚠️ Gemini Connection Failed: {e}")
            return None

    def analyze_exit_reason(self, instrument, exit_type, entry, exit_price, pnl_r, trend, rsi):
        """
        Analyzes why a trade ended (SL HIT / TARGET HIT) and provides a post-trade review.
        """
        if not self.enabled: return None

        try:
            prompt = f"""
            You are a Trading Coach. A trade on {instrument} occurred.
            
            Result: {exit_type}
            Entry: {entry} | Exit: {exit_price}
            PnL: {pnl_r}R
            Trend Context: {trend}
            RSI at Exit: {rsi:.1f}
            
            Provide a strict JSON output explaining the likely cause.
            
            Output JSON format:
            {{
                "reason": "Concise technical reason (max 15 words)",
                "lesson": "One short actionable lesson",
                "verdict": "Good Exit" | "Bad Luck" | "Premature"
            }}
            """
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 150,
                    "responseMimeType": "application/json"
                }
            }
            
            response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}", 
                headers={"Content-Type": "application/json"}, 
                json=payload, timeout=5
            )
            
            if response.status_code == 200:
                text = response.json()['candidates'][0]['content']['parts'][0]['text']
                text = text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            return None
        except Exception:
            return None

    def evaluate_trade_quality(self, market_context, signal_data):
        """
        AI Trade Quality Filter — Institutional-grade validation.
        
        Does NOT generate signals, change direction, or modify SL/RR.
        Only returns ACCEPT or RESTRICT with confidence score.
        
        Args:
            market_context: dict with RSI, ATR, EMA position, VWAP distance, etc.
            signal_data: dict with direction, entry, SL, target, gear
            
        Returns:
            dict: {"decision": "ACCEPT"|"RESTRICT", "confidence": 0-100, "reasons": [...]}
            or None on failure (caller should treat as ACCEPT)
        """
        if not self.enabled:
            return None

        try:
            context_json = json.dumps(market_context, indent=2, default=str)
            signal_json = json.dumps(signal_data, indent=2, default=str)

            prompt = f"""You are an institutional intraday trade quality filter.

Your role:
Evaluate whether the proposed trade aligns with current market structure and context.

IMPORTANT RULES:
- Do NOT predict market direction.
- Do NOT modify entry, SL, or RR.
- Do NOT generate a new trade.
- Do NOT explain market theory.
- Only evaluate trade quality.

You must return output strictly in this JSON format:
{{
    "decision": "ACCEPT" or "RESTRICT",
    "confidence": 0-100,
    "reasons": ["reason 1", "reason 2", "reason 3"]
}}

Evaluation Criteria:
- Is the trade aligned with primary trend?
- Is it late in an expansion leg?
- Is momentum supportive or exhausted?
- Is volatility expanding or fading?
- Is price overextended from VWAP or session extremes?
- Is this occurring during unstable transition phase?

Market Context:
{context_json}

Proposed Signal:
{signal_json}"""

            import time
            max_retries = 3
            base_delay = 2

            # === GROQ API (OpenAI-compatible) ===
            groq_api_key = os.getenv("GROQ_API_KEY", "")
            if not groq_api_key:
                print("[WARN] GROQ_API_KEY not set. Skipping AI filter.")
                return None

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_api_key}"
            }
            url = "https://api.groq.com/openai/v1/chat/completions"

            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are an institutional intraday trade quality filter. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
            }

            for attempt in range(max_retries):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=10)

                    if response.status_code == 200:
                        result = response.json()
                        text = result['choices'][0]['message']['content']
                        text = text.replace('```json', '').replace('```', '').strip()
                        parsed = json.loads(text)

                        # Validate response structure
                        decision = parsed.get('decision', 'ACCEPT').upper()
                        confidence = int(parsed.get('confidence', 50))
                        reasons = parsed.get('reasons', [])

                        if decision not in ('ACCEPT', 'RESTRICT'):
                            decision = 'ACCEPT'
                        confidence = max(0, min(100, confidence))

                        return {
                            "decision": decision,
                            "confidence": confidence,
                            "reasons": reasons if isinstance(reasons, list) else [str(reasons)]
                        }

                    elif response.status_code == 429:
                        print(f"[QUOTA] Groq 429. Retry in {base_delay}s...")
                        time.sleep(base_delay)
                        base_delay *= 2
                        continue
                    else:
                        print(f"[ERROR] Groq API {response.status_code}: {response.text[:200]}")
                        return None

                except Exception as req_err:
                    print(f"[ERROR] Groq request error: {req_err}")
                    if attempt < max_retries - 1:
                        time.sleep(base_delay)
                        continue
                    return None

            return None

        except Exception as e:
            print(f"⚠️ Trade quality evaluation failed: {e}")
            return None


# Global Instance
gemini = GeminiHelper()
