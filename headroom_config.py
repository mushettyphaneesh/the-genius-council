"""
Centralized configuration for Headroom compression and model routing.

Token budget target: ~12,000 tokens per evaluation run (down from 71k).
Achieved via:
  1. Only ONE agent (repo_analyzer) ever reads raw source code
  2. Headroom compresses everything before it touches any LLM

Cost strategy:
  - Featherless Premium ($25/mo, promo BOA26 = free month):
      Unlimited tokens, 4 concurrent connections, 32K context.
      Powers ALL Stage 1 + Stage 2 agents (8 of 9 agents).
  - AI/ML API ($10 credits):
      Pay-per-token, used ONLY for Head Judge arbitration (0-1 calls/eval).
      $10 lasts hundreds of evaluations.
"""

# ---------------------------------------------------------------------------
# Model routing — Cheap tier (Featherless, unlimited tokens)
# ---------------------------------------------------------------------------
# Featherless is the primary provider for ALL Stage 1 + Stage 2 agents.
# Unlimited monthly tokens with the Premium plan ($25/mo, promo BOA26).
# 4 concurrent connections — perfectly matches our 4 parallel Stage 2 judges.
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
FEATHERLESS_MODEL = "Qwen/Qwen2.5-72B-Instruct"

# AI/ML API as fallback cheap provider (pay-per-token)
AIML_BASE_URL = "https://api.aimlapi.com/v1"
AIML_CHEAP_MODEL = "Qwen/Qwen2.5-72B-Instruct"

# ---------------------------------------------------------------------------
# Model routing — Smart tier (AI/ML API, pay-per-token)
# ---------------------------------------------------------------------------
# Used ONLY by the Head Judge for final arbitration / debate protocol.
# At most 1 call per evaluation → $10 in credits lasts hundreds of evals.
SMART_MODEL_AIML = "meta-llama/Llama-3.3-70B-Instruct"
SMART_BASE_URL = "https://api.aimlapi.com/v1"

# Fallback: Google Gemini (if no AIMLAPI_API_KEY is set)
SMART_MODEL_GOOGLE = "gemini-1.5-pro"

# ---------------------------------------------------------------------------
# Compression settings
# ---------------------------------------------------------------------------
# Model name passed to headroom.compress() for tokenizer alignment
COMPRESSION_MODEL = "Qwen/Qwen2.5-72B-Instruct"

# Maximum characters of README to send to fraud_detector
FRAUD_README_MAX_CHARS = 2000

# Maximum number of recent commits to inspect
MAX_COMMITS = 20

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
WEIGHTS = {
    "business": 0.25,
    "innovation": 0.20,
    "band": 0.20,
    "demo": 0.15,
    "code": 0.20,
}

# Debate is triggered when the spread between judge scores exceeds this
DEBATE_THRESHOLD = 20

# Fraud abort threshold (0-100)
FRAUD_ABORT_THRESHOLD = 60

# ---------------------------------------------------------------------------
# Recommendation tiers
# ---------------------------------------------------------------------------
RECOMMENDATION_TIERS = [
    (85, "Top 10 candidate"),
    (70, "Strong submission"),
    (55, "Average submission"),
    (0, "Below threshold"),
]

# ---------------------------------------------------------------------------
# Headroom config
# ---------------------------------------------------------------------------
HEADROOM_CONFIG = {
    "model": "Qwen/Qwen2.5-72B-Instruct",
    "target_tokens": 8000,   # Compress aggressively to stay under 32k
}

