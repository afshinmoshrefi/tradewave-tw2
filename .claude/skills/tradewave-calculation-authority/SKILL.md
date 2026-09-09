---
name: tradewave-calculation-authority
description: Preserve TradeWave as the sole authority for every mathematical result it already calculates. Use when TradeWave or SMN work consumes, displays, compares, tests, changes, or proposes financial calculations, statistics, seasonal studies, projections, scores, or chart values. Allows genuinely new calculations only after verifying TradeWave does not already provide them.
---

# TradeWave Calculation Authority

## Owner Requirement

Afshin explicitly reaffirmed this rule on September 9, 2026. It applies to
100 percent of the mathematical results TradeWave already calculates.

Consume the authoritative TradeWave result. Never implement that calculation
again in SMN, a content generator, browser, chart renderer, agent, helper,
fallback, or separate verification engine. Matching formulas or matching some
sample results does not authorize a duplicate implementation.

If TradeWave appears wrong, document a TradeWave bug and discuss the proposed
change with Afshin. A calculation change must be agreed with him and made in
the TradeWave engine. Do not silently correct its output downstream.

Genuinely new calculations that TradeWave does not already provide are allowed
within the authorized task. Establish that they are new before implementing.
Renaming a result, using a different model, or selecting a different historical
sample does not turn an existing calculation into a new one.

## Apply Before Implementation or Review

1. Identify every mathematical output needed by the task. Check the existing
   engine code, API/export contracts and product knowledge for its owner and
   definition. An absent API field alone does not establish that the engine
   lacks the calculation. If ownership is uncertain, resolve it before writing
   the formula; continue independent writing or visual work meanwhile.
2. For existing TradeWave calculations, obtain the engine response or a
   traceable retained export of that response. Raw price history is not a
   substitute for an existing TradeWave result. An unavailable endpoint is an
   integration gap, not permission to rebuild its mathematics in the client.
3. Preserve the complete study identity: instrument and series, direction,
   start/end window and duration, selected historical years and election mode,
   data timestamp, and engine conventions. For an article recreation, preserve
   the original selected study. Request any additional sample from TradeWave
   and label that comparison; do not silently replace the primary study.
4. Pass engine values through to writing and charts. Labels, layout, colors,
   responsive geometry and display formatting are presentation work. Keep
   original numerical values available; do not introduce new smoothing,
   normalization, aggregation, probabilities, date snapping or projection
   formulas for a result TradeWave already provides.
5. Verify the result by comparing the consumed and displayed values with the
   authoritative response for the same study, including preserved precision
   and documented display formatting. Trace each existing metric and plotted
   series to that response. Use recorded engine responses for client tests;
   do not calculate expected returns with a second formula. Internal
   consistency or visual approval cannot establish TradeWave fidelity.
6. If a source result is missing, the study identity differs, or values disagree,
   hold the affected article/output and investigate. Never silently fall back
   to a local calculation. Existing published defects require a reported scope
   and an authorized repair; this skill does not authorize production writes.

## Existing Duplicates and Suspected Engine Bugs

When a duplicate is discovered, identify affected callers and outputs and mark
the numerical implementation unverified against TradeWave. Within an authorized
fix, replace duplicate calculations with engine data consumption and verify
value fidelity. Do not change the engine merely to make a client test pass.
Discuss any actual engine calculation change with Afshin before implementation;
existing explicit authorization for that exact change does not need repeating.

For a calculation confirmed absent from TradeWave, document the absence and the
new result's meaning and source. It may use existing engine results as inputs,
but it must not replace or relabel them as a corrected version. Follow the task's
existing development and release scope.

## Relevant Failure to Prevent

The September 8 SMN recreation independently derived seasonal returns from
daily prices. It chose the preceding session for a non-trading end date while
TradeWave used the next trading session. A client test expected the duplicate
implementation's rule, so passing tests concealed the disagreement. The same
workflow replaced a 15-midterm-year study with a 20-consecutive-year study.
Neither behavior was justified by a writing or chart upgrade.

The maintained incident evidence and architecture live in
`docs/TRADEWAVE_ECOSYSTEM.md`, section 1 and the September 9 SMN correction.
This skill is a required agent workflow, not an implemented runtime guard.
Do not claim future violations are impossible merely because it is installed.
