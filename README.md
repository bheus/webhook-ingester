# webhook-ingester

Tiny Flask + gunicorn service that receives webhooks from third-party providers, verifies each provider's signature, and pushes the raw event JSON to Loki with structured labels for downstream alerting.

Currently supports:

- **Stripe** at `POST /webhooks/stripe` — verified via `Stripe-Signature` (`stripe.Webhook.construct_event`)
- **Resend** at `POST /webhooks/resend` — verified via Svix headers (`svix-id` / `svix-timestamp` / `svix-signature`)

Health check at `GET /healthz`.

## Loki labels

Each event is pushed as a single stream with labels:

```
job=webhooks  provider={stripe|resend}  event_type=<provider's event type>
```

The full event JSON is the log line. Alerts then run `count_over_time` over `{provider="..."} |= "event_type"`.

## Deployment

Deployed via Portainer Git stack on `apple-pi.lan`. Cloudflared tunnel routes `webhooks.builtbybrendan.com` → `http://localhost:8019`.

**Portainer Git stacks fetch only the compose file**, so `stack.env` does not exist on the host. Set environment variables (`STRIPE_WEBHOOK_SECRET`, `RESEND_WEBHOOK_SECRET`, optionally `LOKI_URL`) in Portainer's stack env editor — compose substitutes them at deploy time.

Local dev (outside Portainer):

```bash
git clone git@github.com:bheus/webhook-ingester.git
cd webhook-ingester
cp stack.env.example stack.env
# fill in STRIPE_WEBHOOK_SECRET and RESEND_WEBHOOK_SECRET
export $(grep -v '^#' stack.env | xargs) && docker compose up -d --build
```

Loki is reached via `host.docker.internal:3100` (Loki bound on the host).

## Webhook configuration

- **Stripe**: dashboard → Developers → Webhooks → Add endpoint
  - URL: `https://webhooks.builtbybrendan.com/webhooks/stripe`
  - Events: `charge.dispute.created`, `charge.failed`, `invoice.payment_failed`
  - Copy signing secret to `STRIPE_WEBHOOK_SECRET`
- **Resend**: dashboard → Webhooks → Add endpoint
  - URL: `https://webhooks.builtbybrendan.com/webhooks/resend`
  - Events: `email.bounced`, `email.complained`
  - Copy signing secret to `RESEND_WEBHOOK_SECRET`

## Staged rollout

A provider with an empty secret returns `503` (and does not crash). Useful for landing the stack before both dashboards are configured.
