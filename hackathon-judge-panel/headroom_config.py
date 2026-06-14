"""
Centralized configuration for Headroom compression and model routing.

Token budget target: ~12,000 tokens per evaluation run (down from 71k).
Achieved via:
  1. Only ONE agent (repo_analyzer) ever reads raw source code
  2. Headroom compresses everything before it touches any LLM
"""

# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------
CHEAP_MODEL = "Qwen/Qwen2.5-72B-Instruct"
CHEAP_BASE_URL = "https://api.aimlapi.com/v1"

# Smart model — used ONLY by the Head Judge for arbitration.
# Primary: AI/ML API (preferred — keeps the entire pipeline on one provider).
# Fallback: Google Gemini 1.5 Pro (if AIMLAPI_API_KEY is missing).
SMART_MODEL_AIML = "meta-llama/Llama-3.3-70B-Instruct"
SMART_BASE_URL = "https://api.aimlapi.com/v1"
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
