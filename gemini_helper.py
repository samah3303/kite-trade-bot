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
        AI Trade Quality Filter — Deterministic 5-Point Rubric (v3.1).
        
        Scores trade on 5 criteria (0-2 each, total 0-10).
        Total >= 6 → ACCEPT, < 6 → RESTRICT.
        
        Returns:
            dict with decision, confidence, total_score, sub-scores, reasons
            or None on failure (caller should treat as ACCEPT)
        """
        if not self.enabled:
            return None

        try:
            context_json = json.dumps(market_context, indent=2, default=str)
            signal_json = json.dumps(signal_data, indent=2, default=str)

            prompt = f"""You are an institutional quantitative risk manager. Evaluate the provided 17-parameter market context JSON for the proposed trade.
Do not provide opinions. Score the trade strictly using this 5-point rubric (0 to 2 points each):

1. Trend Alignment:
   (2 = Perfectly aligned with VWAP and Structure, 1 = Neutral/Early shift, 0 = Counter-trend)
2. Momentum State (RSI):
   (2 = Supportive slope, 1 = Flat, 0 = Exhausted/Diverging)
3. VWAP Proximity:
   (2 = Near VWAP/Fresh cross, 1 = Moderate distance, 0 = Overextended by >0.4%)
4. Expansion Phase:
   (2 = Early impulse <1.5x ATR, 1 = Mid-trend, 0 = Late cycle >2.5x ATR)
5. Structure Quality:
   (2 = Clean HH-HL / LL-LH, 1 = Mixed, 0 = Choppy/Overlapping)

Calculate the Total Score (0-10).
If Total Score >= 6: Output "decision": "ACCEPT"
If Total Score < 6: Output "decision": "RESTRICT"

Return ONLY this JSON — no other text:
{{"trend_score": <0-2>, "momentum_score": <0-2>, "vwap_score": <0-2>, "phase_score": <0-2>, "structure_score": <0-2>, "total_score": <0-10>, "decision": "ACCEPT" or "RESTRICT", "confidence": <total_score * 10>, "reasons": ["reason1", "reason2", "reason3"]}}

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
                    {"role": "system", "content": "You are an institutional quantitative risk manager. Return ONLY valid JSON with the exact schema requested. No additional text."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.05,
                "max_tokens": 400,
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

                        # Extract sub-scores
                        trend_score = max(0, min(2, int(parsed.get('trend_score', 0))))
                        momentum_score = max(0, min(2, int(parsed.get('momentum_score', 0))))
                        vwap_score = max(0, min(2, int(parsed.get('vwap_score', 0))))
                        phase_score = max(0, min(2, int(parsed.get('phase_score', 0))))
                        structure_score = max(0, min(2, int(parsed.get('structure_score', 0))))

                        # Recompute total to prevent LLM math errors
                        total_score = trend_score + momentum_score + vwap_score + phase_score + structure_score
                        decision = "ACCEPT" if total_score >= 6 else "RESTRICT"
                        confidence = total_score * 10

                        reasons = parsed.get('reasons', [])
                        if not isinstance(reasons, list):
                            reasons = [str(reasons)]

                        return {
                            "decision": decision,
                            "confidence": confidence,
                            "total_score": total_score,
                            "trend_score": trend_score,
                            "momentum_score": momentum_score,
                            "vwap_score": vwap_score,
                            "phase_score": phase_score,
                            "structure_score": structure_score,
                            "reasons": reasons,
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
