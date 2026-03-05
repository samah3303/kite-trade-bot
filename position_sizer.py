"""
RIJIN v3.1 — Dynamic Position Sizer

Ties AI rubric score directly to risk allocation:
- Score 8-10: 1.5R (High conviction)
- Score 6-7:  1.0R (Standard)
- Score 0-5:  0.0R (Blocked / RESTRICT)
- Gear 3 bypass: 0.75R-1.0R (fixed, no AI score)
"""


def calculate_risk_multiplier(ai_result, gear="N/A"):
    """
    Returns R-multiple based on AI score and gear.
    
    Args:
        ai_result: dict with 'total_score' and/or 'confidence'
        gear: str, the signal gear name
    
    Returns:
        float: risk multiplier (0.0 = blocked, 0.75-1.5 = active)
    """
    # Gear 3 bypass: fixed risk, no AI score available
    if gear == "GEAR_3_MOMENTUM":
        return 0.75
    
    # Extract score from AI result
    total_score = ai_result.get('total_score', None)
    
    # Fallback: if no rubric score, use confidence / 10
    if total_score is None:
        confidence = ai_result.get('confidence', 50)
        total_score = confidence / 10
    
    # Score-based sizing
    if total_score >= 8:
        return 1.5    # High conviction — step on the gas
    elif total_score >= 6:
        return 1.0    # Standard conviction
    else:
        return 0.0    # Blocked (RESTRICT)


def get_expiry_size_reduction(is_expiry_day, hour, minute):
    """
    Returns size reduction factor for expiry days.
    
    Args:
        is_expiry_day: bool
        hour: int (IST)
        minute: int (IST)
    
    Returns:
        float: multiplier (1.0 = full size, 0.7 = 30% reduction)
    """
    if not is_expiry_day:
        return 1.0
    
    # After 12:00 PM on expiry → 30% size reduction
    if hour >= 12:
        return 0.7
    
    return 1.0


def should_block_gear2_expiry(is_expiry_day, hour, minute):
    """
    Block Gear 2 (mean reversion) signals on expiry afternoons.
    Mean reversion dies on expiry afternoons.
    
    Returns:
        bool: True if Gear 2 should be blocked
    """
    if not is_expiry_day:
        return False
    
    # Block Gear 2 after 1:30 PM on expiry
    if hour > 13 or (hour == 13 and minute >= 30):
        return True
    
    return False
