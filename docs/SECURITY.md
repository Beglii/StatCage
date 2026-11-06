# StatCage security plan

StatCage is a public site that calls a paid LLM API. The two goals are:

1. **Nobody can run up the LLM bill**, on purpose or by accident.
2. **The usual web app basics**: secrets, database, server and dependencies stay locked down.

Status: `[x]` done, `[ ]` planned (the phase that builds it is in brackets).

## 1. LLM cost protection

Layers, in the order a request meets them. Each one catches what the one before missed.

### No free-text prompts
- [ ] Users pick two fighters from a list. The API accepts only two `fighter_id`s, and Pydantic rejects anything that isn't a known 16-hex ID. *(phase 4)*
- [ ] No text box ever reaches the LLM, so StatCage can't be used as a free general chatbot and there is nothing to prompt-inject. *(phase 4-5)*

### Cache
- [ ] Each matchup is answered by the agent once, saved in Postgres, and served from the cache after that. The cache resets on the weekly data refresh. *(phase 4)*
- [ ] Upcoming card fights are precomputed once per week, so most traffic never calls the LLM. *(phase 6)*

### Free answer first
- [ ] The baseline model's probability (no API cost) is always shown. The agent's explanation is the only paid part. *(phase 4)*
- [ ] When any limit is hit, users still get the baseline answer plus a "detailed analysis is busy" message. *(phase 4-5)*

### Rate limits
- [ ] Every quota check goes through one function, `can_spend(requester)`. A requester starts as an IP address and later becomes a user account (see section 3). *(phase 4)*
- [ ] Per requester: new AI analyses per hour and per day (starting point: 5/hour, 20/day). Cache hits and baseline predictions don't count. *(phase 4)*
- [ ] AWS WAF rate-based rule on CloudFront to block floods before they reach the server. *(phase 6)*

### Bot check
- [ ] Cloudflare Turnstile on the predict button, verified by the backend before any LLM call. *(phase 5)*

### Global daily budget
- [ ] After each agent run, record the tokens Claude reports, convert them to dollars, and add them to a daily spend counter in Postgres. *(phase 4)*
- [ ] When the daily cap is reached, AI explanations turn off until midnight UTC. The cap gets set from real tokens-per-prediction measured in phase 3. *(phase 4)*

### Per-request limits
- [ ] `max_tokens` on every Claude call. *(phase 3)*
- [ ] At most ~6 tool calls per prediction. *(phase 3)*
- [ ] Timeout on every Claude call. *(phase 3)*
- [ ] Only a few agent runs at once; extra requests get "busy". *(phase 4)*

### Backstops outside the code
- [ ] Monthly spend limit set in the Anthropic Console. *(phase 3, before the first real key is used)*
- [ ] AWS billing alarm emailing on unexpected spend. *(phase 6)*

## 2. Web app basics

### Secrets
- [x] Real secrets live only in `.env`, which is in `.gitignore`. `.env.example` holds placeholders only.
- [x] Code reads the database password from the environment (`statcage/db.py`), never from source.
- [ ] GitHub secret scanning and push protection turned on for the repo.
- [ ] The Anthropic API key exists only on the backend. The frontend never calls Claude directly. *(phase 3-4)*

### Database
- [x] Schema rules (primary keys, foreign keys, CHECKs) reject bad rows even if code skips `validate.py`.
- [x] Local Postgres listens on `127.0.0.1` only, so it isn't reachable from other devices on the network.
- [ ] The API connects as a read-only Postgres user (`SELECT` only). Only the loader can write. *(phase 4)*
- [ ] On the server, Postgres has no published port; only the API container can reach it over Docker's private network. *(phase 6)*

### Server and network
- [ ] Firewall allows only HTTPS (443) and SSH (22, key-only, no passwords). *(phase 6)*
- [ ] HTTPS everywhere. *(phase 6)*
- [ ] CORS allows only `statcage.com`. *(phase 4)*
- [ ] Users see generic error messages; stack traces and SQL go to server logs only. *(phase 4)*

### Dependencies and monitoring
- [x] `uv.lock` pins exact package versions.
- [ ] Dependabot alerts for vulnerable dependencies.
- [ ] Logs and a simple daily summary: LLM spend, cache hit rate, rate-limit hits, errors. *(phase 4-6)*

## 3. Accounts and payments roadmap

Users never see LLM tokens. They spend **analyses**: one analysis is one new AI explanation, whatever it costs in tokens. Cached and baseline predictions are always free. The cost protections in section 1 apply at every stage.

| Stage | Requester | Limit | Paid |
|---|---|---|---|
| 1. Launch | IP address | a few free analyses per day | no |
| 2. Accounts | signed-in user | free analyses per month per account | no |
| 3. Payments | signed-in user | free amount plus credit packs | yes |

Move up a stage only with evidence: stage 2 once real users share IPs or dodge IP limits, stage 3 once real users keep hitting the free limit and the real cost per analysis is known.

### Stage 2: accounts
- [ ] Use an auth provider (Clerk, Auth0, Supabase Auth or AWS Cognito), not homemade login. Google sign-in makes fake free accounts harder.
- [ ] FastAPI verifies the provider's JWT signature on every request before doing anything.
- [ ] `can_spend(requester)` switches from IP to user ID; nothing else in the quota logic changes.

### Stage 3: payments
- [ ] Check Stripe's restricted businesses list first: fight predictions next to betting odds can count as gambling-related. Position StatCage as analytics and entertainment, not betting advice.
- [ ] Terms of service, privacy policy and refund policy published before taking money.
- [ ] Stripe Checkout (hosted page), so card numbers never touch our server.
- [ ] Credit packs, not subscriptions, to start. Pack sizes chosen so Stripe's fixed fee per payment doesn't eat most of the price.
- [ ] Credits are added only by a Stripe webhook whose signature the API verifies. The frontend can never say "payment succeeded".
- [ ] Spending a credit happens in a database transaction, so two requests at once can't spend the same credit twice.
- [ ] Stripe Radar plus Turnstile on the buy button against card testing bots.

## 4. Fantasy matchup rules

These limits apply only to fantasy matchups. Real booked fights are always predicted, even across divisions. The API enforces every rule, so calling it directly can't bypass the fighter picker.

- [ ] Block men vs. women matchups, using each fighter's category from their `womens` fight history. *(phase 4)*
- [ ] Block matchups more than one weight class apart. *(phase 4)*
- [ ] Each fighter's division is their most recent standard division as of the chosen date; catch weight and open weight fights don't count. Fighters without a standard division can't be picked. *(phase 4)*
- [ ] Warn when the two profile dates are 5 or more years apart. Tune this after trying real matchups. *(phase 4-5)*
- [ ] Label results "Fantasy matchup: for fun, not validated". Accuracy claims cover real fights only. *(phase 5)*

Weight class order: Strawweight, Flyweight, Bantamweight, Featherweight, Lightweight, Welterweight, Middleweight, Light Heavyweight, Heavyweight.

## If something leaks

1. Revoke the key or password at its source first (Anthropic Console, AWS, Postgres), then create a new one.
2. Put the new value in `.env` / the server environment, never in a committed file.
3. Check usage dashboards for activity during the leak window.
4. Removing a secret from the latest commit is not enough: it is still in git history. Treat it as public once pushed.
