"""
Retrieval, relevance filtering, and confidence estimation constants.
Centralized in one constants file as required by architecture specifications.
"""
from typing import Optional


# Relative score cutoff ratio:
# Drops any candidate chunk whose vector score is less than this fraction of the top candidate's vector score.
# E.g. with 0.75 ratio and top_score=0.88, any chunk scoring below 0.66 is dropped.
RELATIVE_SCORE_CUTOFF_RATIO: float = 0.75

# Retrieval strength thresholds:
# Based on top score and its margin over the second result.
STRENGTH_HIGH_MIN_SCORE: float = 0.70
STRENGTH_HIGH_MIN_MARGIN: float = 0.08
STRENGTH_HIGH_SOLO_SCORE: float = 0.75

STRENGTH_MODERATE_MIN_SCORE: float = 0.50
STRENGTH_MODERATE_MIN_MARGIN: float = 0.03


def compute_retrieval_strength(top_score: float, second_score: Optional[float] = None) -> str:
    """
    Computes qualitative retrieval strength based on the top vector score
    and its margin over the second candidate result.

    Thresholds:
    - High: top_score >= 0.70 and margin >= 0.08 (or top_score >= 0.75 when solo result)
    - Moderate: top_score >= 0.50 and margin >= 0.03
    - Low: otherwise

    Returns: 'High', 'Moderate', or 'Low'.
    """
    if second_score is not None:
        margin = max(0.0, top_score - second_score)
    else:
        margin = top_score

    if (top_score >= STRENGTH_HIGH_MIN_SCORE and margin >= STRENGTH_HIGH_MIN_MARGIN) or top_score >= STRENGTH_HIGH_SOLO_SCORE:
        return "High"
    elif top_score >= STRENGTH_MODERATE_MIN_SCORE and margin >= STRENGTH_MODERATE_MIN_MARGIN:
        return "Moderate"
    return "Low"
