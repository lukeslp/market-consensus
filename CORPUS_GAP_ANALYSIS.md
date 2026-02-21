# Foresight Corpus Gap Analysis

## What IS Being Stored

| Data | Table | Notes |
|------|-------|-------|
| Prediction direction, confidence, reasoning | `predictions` | ✅ Stored for every provider + consensus |
| Initial price at prediction time | `predictions` | ✅ |
| Actual price + direction (post-evaluation) | `predictions` | ✅ When target window passes |
| Sub-agent votes (analysis phase) | `agent_votes` | ✅ NEW - direction, confidence, reasoning, role |
| Synthesis votes | `agent_votes` | ✅ NEW - direction, confidence, reasoning |
| Council debate round (vote totals, transcript) | `debate_rounds` | ✅ NEW |
| Synthesis debate round (vote totals, transcript) | `debate_rounds` | ✅ NEW |
| Price snapshots per cycle | `prices` | ✅ |
| Provider weights per cycle | `debate_rounds.provider_weights` | ✅ NEW |

## What IS NOT Being Stored (Gaps)

### Gap 1: Raw LLM Responses
- `predictions.raw_response` column EXISTS but is NEVER populated
- `agent_votes.raw_response` column EXISTS but is NEVER populated
- The actual LLM response text (before JSON parsing) is discarded in both
  `generate_prediction_swarm()` and `synthesize_council_swarm()`
- **Impact**: Losing the full response text, any non-JSON commentary, token usage, etc.

### Gap 2: Discovery Phase Data
- Stock discovery debate votes (which providers voted for which tickers) are logged
  but NOT persisted to any table
- Discovery sub-agent persona votes (momentum scanner, news catalyst scout, etc.)
  are completely lost
- **Impact**: Can't analyze which providers are best at stock discovery

### Gap 3: Market Direction Predictions
- Individual provider market direction votes are stored in `predictions` ✅
- But NO `agent_votes` or `debate_rounds` rows are created for market direction
- **Impact**: Market direction debate data is less structured than stock debates

### Gap 4: Prompt Text
- The actual prompts sent to each LLM are constructed inline and discarded
- No record of what prompt template was used for each prediction
- **Impact**: Can't do prompt engineering analysis or A/B testing

### Gap 5: Model Metadata
- `agent_votes.model` stores the model name ✅
- But `predictions` table has NO model column - only provider name
- Can't distinguish between model versions over time

### Gap 6: Token Usage / Latency
- No timing data on how long each LLM call took
- No token count data (input/output tokens)
- **Impact**: Can't optimize for cost or speed

### Gap 7: Stock Data Context
- The historical price data and stock_data dict sent to each LLM is not stored
- Only `initial_price` is saved, not the full close/volume arrays
- **Impact**: Can't reproduce what the LLM "saw" when making predictions
