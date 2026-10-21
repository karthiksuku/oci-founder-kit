# Discovery: the facts a value case needs

Ask for the smallest set of facts that can change the verdict. Read what you
can from the repository and the founder's billing export first.

## Always needed

| Fact | Why | Typical source |
|---|---|---|
| The decision being made | Sets which numbers matter | Founder |
| Company stage and next milestone (launch, raise, first enterprise deal) | Sets the payback threshold | Founder |
| Customers now and monthly growth | Revenue and per-customer scaling | Founder, billing system |
| Average revenue per account (ARPA) per month | Margin denominator | Founder, billing system |
| Other cost of goods per account: support tools, payment fees, third-party APIs | Without it every margin is cloud-only and overstates true gross margin; say so if it is missing | Founder, accounts |
| Current monthly cloud bill, by line | The baseline | Invoice or billing export |
| Credits or discounts held on the current cloud, with expiry | Fair comparison | Founder |
| Cash on hand and monthly operating spend | Runway | Founder |
| Where customers are and any residency requirement | Region and enterprise readiness | Founder, contracts |

## Needed when relevant

| Situation | Ask for |
|---|---|
| The product calls an AI model | Actions per customer per month, input and output tokens per action, cache share, current model and its price, the quality bar |
| Media, downloads, APIs serving large payloads | Monthly internet egress in GB and where it originates |
| Migration | Services in use, data volume, engineering hours available, a launch or raise in the next 90 days |
| Selling to enterprises | Target industries, deal sizes, deals delayed by security or residency |
| Applying to the Startup Growth Engine | Country of incorporation, whether the company already uses OCI, customers or pilots that validate the product |

## Reading a repository (read-only)

| Look for | It tells you |
|---|---|
| Dockerfile, process manager, framework config | Runtime shape and whether it is container-ready |
| Database drivers, ORM config, migrations | Database engine and extensions to carry across |
| Object storage SDK calls, upload handlers, CDN config | Storage volume and egress-heavy features |
| AI SDK imports and model names | Which models are used and where token counts can be logged |
| Infrastructure as code, CI deploy steps | Current services and migration effort |
| Queue, cache and search clients | Services that need an equivalent |

Do not read secrets, `.env` files or credentials. If usage numbers are not in
the repository, ask; do not infer traffic from code.

## By stage

| Stage | What usually decides it | Keep the case to |
|---|---|---|
| Pre-product | Build-here cost at list price, AI unit cost, credits for experiments | A value check |
| First customers | Durable margin, AI unit cost, migration effort while the code is small | A value check or a model |
| Growing, pre-Series A | Gross margin trend, cost per customer, payback without credits | A model and a value case |
| Selling to enterprises | Deal readiness, residency, go-to-market through Oracle | A value case plus `founder-value-gtm` |

## Questions to avoid

- Questions the invoice or repository already answers.
- Asking for exact numbers when a range would give the same verdict.
- Anything about personal data, credentials or customer contracts beyond what
  the decision needs.
