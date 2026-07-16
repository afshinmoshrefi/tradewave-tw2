"""Complete the API-Dev subscription via Stripe TEST API so the LIVE webhook fires
exactly as a UI checkout would (customer + subscription with product_line=api,tier=dev,
tw2_user_id=<uuid>). Times the webhook's api_tier write."""
import os, sys, json, time
sys.path.insert(0, "/home/flask"); sys.path.insert(0, "/home/flask/web")
import config, stripe, psycopg2
stripe.api_key = config.STRIPE_SECRET_KEY
assert stripe.api_key.startswith("sk_test_"), "NOT A TEST KEY - ABORT"

STATE = "/tmp/claude-0/-home-flask/0a525026-2010-4572-a505-12cf6e7a1966/scratchpad/audit_state.json"
st = json.load(open(STATE))
uid = st["db_user_id"]; email = st["email"]

# Find the dev API price the same way the console does (metadata product_line=api,tier=dev).
price_id = None
for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
    prod = p.product
    md = prod.metadata.to_dict() if hasattr(prod.metadata, "to_dict") else {k: prod.metadata[k] for k in prod.metadata.keys()}
    if (md.get("product_line") or "").lower() == "api" and (md.get("tier") or "").lower() == "dev":
        interval = p.recurring.interval if p.recurring else None
        if interval == "month":
            price_id = p.id; break
print("dev monthly price:", price_id)

# Create customer + attach test card + subscribe (metadata drives the webhook route).
cust = stripe.Customer.create(email=email, name="Apiux Audit",
        payment_method="pm_card_visa",
        invoice_settings={"default_payment_method": "pm_card_visa"},
        metadata={"tw2_user_id": uid})
print("customer:", cust.id)
sub = stripe.Subscription.create(
    customer=cust.id,
    items=[{"price": price_id}],
    metadata={"tw2_user_id": uid, "product_line": "api", "tier": "dev", "interval": "month"},
    expand=["latest_invoice.payment_intent"],
)
print("subscription:", sub.id, "status:", sub.status)
st["stripe_customer_id"] = cust.id; st["stripe_api_sub_id"] = sub.id
json.dump(st, open(STATE, "w"), indent=2, default=str)

# Poll DB for the webhook writing api_tier=dev; time it from subscription create.
t0 = time.time()
con = psycopg2.connect(os.environ["POSTGRES_DSN"]); con.autocommit = True
cur = con.cursor()
final = None
for i in range(30):
    cur.execute("SELECT api_tier, stripe_customer_id FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    if row and row[0] == "dev":
        final = time.time() - t0
        print(f"WEBHOOK api_tier=dev after {final:.1f}s (cust in row: {row[1]})")
        break
    time.sleep(1)
if final is None:
    print("api_tier NOT written after 30s; last row:", row)
con.close()
