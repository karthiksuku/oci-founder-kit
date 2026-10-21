# Migration assessment: aws-terraform

Source clouds: aws (20). Files scanned: 3. Findings: 19, mapped to 15 OCI services (10 equivalent, 5 partial, 0 gap). Unrecognised: 1.

Effort signal: **L** (score 36). Heuristic: low 1, medium 3, high 8 per distinct OCI service; +1 per Kubernetes coupling; +2 per unrecognised resource. S < 12, M < 35, L < 80, XL above.

Container-ready: yes, app/Dockerfile.

## What maps to OCI

| Fit | Complexity | Found | Count | OCI target |
|---|---|---|---:|---|
| partial | high | `aws_cognito_user_pool` | 1 | [OCI IAM identity domains](https://docs.oracle.com/en-us/iaas/Content/Identity/home.htm) |
| partial | medium | `aws_ecs_cluster`, `aws_ecs_service`, `aws_ecs_task_definition` | 3 | [OCI Container Instances](https://docs.oracle.com/en-us/iaas/Content/container-instances/home.htm) |
| partial | medium | `@aws-sdk/client-sqs`, `aws_sqs_queue` | 2 | [OCI Queue](https://docs.oracle.com/en-us/iaas/Content/queue/home.htm) |
| partial | medium | `aws_cloudfront_distribution` | 1 | [Cloudflare@OCI, or Web Application Acceleration at the load balancer](https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?partNumber=B112540) |
| partial | medium | `aws_xray_sampling_rule` | 1 | [OCI Application Performance Monitoring](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/index.html) |
| equivalent | medium | `aws_db_instance` | 1 | [OCI Database with PostgreSQL](https://docs.oracle.com/en-us/iaas/Content/postgresql/home.htm) |
| equivalent | medium | `aws_lb` | 1 | [OCI Flexible Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/home.htm) |
| equivalent | low | `aws_ecr_repository` | 1 | [OCI Container Registry (OCIR)](https://docs.oracle.com/en-us/iaas/Content/Registry/home.htm) |
| equivalent | low | `aws_elasticache_replication_group` | 1 | [OCI Cache (Redis-compatible)](https://docs.oracle.com/en-us/iaas/Content/ocicache/home.htm) |
| equivalent | low | `aws_route53_record` | 1 | [OCI DNS](https://docs.oracle.com/en-us/iaas/Content/DNS/home.htm) |
| equivalent | low | `aws_security_group` | 1 | [Network security groups and security lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm) |
| equivalent | low | `terraform-aws-modules/vpc/aws` | 1 | [Virtual Cloud Network (VCN)](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) |
| equivalent | low | `aws_cloudwatch_log_group` | 1 | [OCI Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/home.htm) |
| equivalent | low | `aws_secretsmanager_secret` | 1 | [OCI Vault secrets](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/managingsecrets.htm) |
| equivalent | low | `@aws-sdk/client-s3`, `aws_s3_bucket` | 2 | [OCI Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/home.htm) |

## Partial fits and gaps

**OCI IAM identity domains** (partial, high): replaces aws_cognito_user_pool.
- OIDC, OAuth 2.0 and SAML are supported; the app changes issuer, client settings and token claims.
- Password hashes are not portable: plan resets or migrate users at next sign-in.
- Hosted sign-in pages, triggers and custom flows need replacements.
- Migration: Bulk-import users, run old and new sign-in in parallel, migrate users as they sign in.

**OCI Container Instances** (partial, medium): replaces aws_ecs_cluster, aws_ecs_service, aws_ecs_task_definition.
- No built-in request-based autoscaling, revisions or traffic splitting; run several instances behind a load balancer, or use OKE when the app needs them.
- Platform features such as deployment slots, managed TLS and built-in sign-in need explicit replacements.
- Migration: Push the same container image to OCIR and run it as container instances behind a load balancer.
- Alternative: `kubernetes` when the app needs autoscaling, rolling deploys or many services.

**OCI Queue** (partial, medium): replaces @aws-sdk/client-sqs, aws_sqs_queue.
- Similar model (visibility timeout, dead-letter queue) with a different API and SDK.
- Check FIFO, sessions and ordering guarantees you rely on.
- Migration: Drain the old queue while producers switch; keep consumers idempotent.

**Cloudflare@OCI, or Web Application Acceleration at the load balancer** (partial, medium): replaces aws_cloudfront_distribution.
- OCI has no first-party global CDN in this map. Cloudflare services are sold and billed through OCI as Cloudflare@OCI (price list parts B112540 to B112555, checked 2026-10-21).
- Web Application Acceleration adds caching and compression at an OCI load balancer, not at a global edge.
- Migration: Recreate cache rules and origins in the chosen CDN; cut over by DNS.

**OCI Application Performance Monitoring** (partial, medium): replaces aws_xray_sampling_rule.
- OpenTelemetry instrumentation moves most easily; vendor-specific agents need replacing.
- Migration: Switch exporters to the APM endpoint.

## Application code that calls cloud SDKs

These need code changes, or a compatible API, before the app runs on OCI.

| Package | Ecosystem | Used for | File |
|---|---|---|---|
| `@aws-sdk/client-s3` | npm | object-storage | app/package.json:4 |
| `@aws-sdk/client-sqs` | npm | message-queue | app/package.json:5 |

## Not recognised

Cloud resources the service map does not cover yet. Review each by hand.

- `aws_appconfig_application` (terraform) in main.tf:94

## Next steps

1. Confirm the inventory with the team: anything created by hand in a console will not appear here.
2. Settle every partial fit and gap above before choosing dates.
3. Plan the migration with `oci-migrate-plan`, and price both sides with `founder-value`.

Service map checked 2026-10-21 against oracle/oci 9.10.0. A planning aid, not a guarantee of compatibility.
