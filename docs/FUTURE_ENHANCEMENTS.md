# Future Enhancements

## Social publishing beyond the Daily AI Pick

The canonical Daily AI Pick already publishes directly to X from the production
web server. The following expansion is intentionally deferred:

1. **Owner-approved TradeWave UI publishing**
   - Build an authenticated, owner-only composer that starts with deterministic
     TradeWave facts, allows editing and preview, and publishes only after an
     explicit confirmation.
   - Keep X credentials server-side. Use a durable social outbox for validation,
     deduplication, retries, audit history, and provider response tracking.

2. **Seasonal Market News editorial publishing**
   - Select only already-published SMN articles with durable canonical URLs.
   - Let Hermes recommend and draft posts, but require manual approval initially.
   - Send approved posts through the same social outbox with per-article
     deduplication and performance tracking.

These are distribution enhancements, not launch blockers.
