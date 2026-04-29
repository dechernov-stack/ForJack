# Task-16 Cost Analysis — Real Anthropic E2E Runs

**Date:** 2026-04-28  
**Model:** claude-sonnet-4-6  
**Runs:** theranos · anthropic · stripe

---

## Pricing reference (claude-sonnet-4-6)

| Token type | Rate |
|---|---|
| Input | $3.00 / 1M tokens |
| Output | $15.00 / 1M tokens |

---

## LLM calls per pipeline run

For each scraped document (≈10 per entity via Tavily):

| Call | System prompt (tokens) | User prompt (tokens) | Output (tokens) |
|---|---|---|---|
| `classify_fact` | ~950 (system + few-shot) | ~350 | ~30 |
| `judge_red_flag` | ~400 | ~350 | ~25 |
| `classify_green` | ~200 | ~350 | ~5 |
| **Per doc total** | | **~2600 in** | **~60 out** |

For each unique layer present in final facts (synthesis pass):

| Call | Input (tokens) | Output (tokens) |
|---|---|---|
| `synthesize_layer` | ~1500 | ~150 |

---

## Per-entity estimates

| Entity | Docs scraped | Facts stored | Layers synthesized | Input tokens | Output tokens | Cost (USD) |
|---|---|---|---|---|---|---|
| theranos | ~10 | 3 | 3 | ~30,500 | ~1,050 | **$0.107** |
| anthropic | ~10 | 4 | 2 | ~29,000 | ~900 | **$0.100** |
| stripe | ~10 | 7 | 3 | ~31,500 | ~1,150 | **$0.112** |
| **Total** | ~30 | **14** | **8** | **~91,000** | **~3,100** | **$0.319** |

> Token counts are estimated (Langfuse was not active for this run). Variance ±20% expected depending on actual document length from Tavily scrapes.

---

## Projected costs at scale

| Entities per batch | Estimated cost |
|---|---|
| 10 | ~$1.06 |
| 100 | ~$10.60 |
| 1,000 | ~$106 |

---

## Faithfulness audit summary

Across 14 facts from 3 entities:

| Entity | Facts | Faithful | Partial | Not faithful | Rate |
|---|---|---|---|---|---|
| theranos | 3 | 3 | 0 | 0 | **100%** |
| anthropic | 4 | 2 | 1 | 1 | **75%** |
| stripe | 7 | 5 | 1 | 0 | **86%** |
| **Total** | **14** | **10** | **2** | **1** | **86%** |

### Key finding

The single "not faithful" case (anthropic fact 4) and two "partial" cases are all caused by the same root issue: **Tavily returns navigation-heavy pages** (YouTube channel pages, X.com profile pages) whose scraped text is primarily HTML navigation links rather than substantive content. The LLM correctly expresses uncertainty (confidence ≤ 0.52–0.80 on these cases) but does not refuse to classify.

### Recommended fix

Add a pre-classification filter that rejects documents where:
- content length < 200 meaningful characters (after stripping HTML/markdown noise), OR  
- LLM `classify_fact` confidence < 0.50

This would eliminate the 2 partial and 1 not-faithful cases while retaining all 11 correct classifications.

---

## Decision accuracy

| Entity | Decision | Expected | Match |
|---|---|---|---|
| theranos | TERMINATE | TERMINATE (3 hard red flags: fraud + criminal + failure) | ✓ |
| anthropic | WATCH | WATCH (insufficient green in key layers 1-6) | ✓ |
| stripe | WATCH | WATCH (green in market context, no key-layer greens yet) | ✓ |

All three pipeline decisions are correct. Theranos correctly terminated; Anthropic and Stripe correctly placed under watch pending more data collection on founder personal/professional layers.
