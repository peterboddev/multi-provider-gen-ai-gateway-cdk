# Multi-Provider Gen AI Gateway (CDK)

A slim, CDK-based multi-provider LLM gateway with latency-based routing and automatic failover between AWS Bedrock (Claude) and OpenAI (GPT).

## Architecture

```
Client → CloudFront → ALB → ECS Fargate (FastAPI)
                                   ├── Bedrock (Claude via invoke-model)
                                   └── OpenAI (GPT via api.openai.com)
```

The FastAPI app tracks latency/errors per provider and routes to the healthier one. If one provider exceeds a latency threshold or error rate, traffic shifts to the other automatically.

Bedrock uses the native Anthropic Messages API (invoke-model with SigV4 auth). The gateway translates between OpenAI Chat Completions format (client-facing) and Anthropic Messages format (Bedrock-facing) internally.

## What's Included

- **CDK (TypeScript)** infrastructure — VPC, ECS Fargate, ALB, CloudFront, Secrets Manager, CloudWatch
- **FastAPI (Python)** application — OpenAI-compatible `/v1/chat/completions` endpoint
- **Latency-based routing** with sliding window health tracking
- **Automatic failover** between Bedrock and OpenAI
- **API key authentication** via Secrets Manager
- **CloudWatch dashboard** with routing metrics (EMF)
- **Structured JSON logging** with routing decision visibility

## What's NOT Included

No LiteLLM, no Redis, no RDS, no EKS, no admin UI, no chat history, no Okta auth.

## Prerequisites

- AWS account with Bedrock model access enabled (Claude Haiku 4.5)
- Node.js 20+
- Docker (for building the container image)
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS credentials configured

## Quick Start

### 1. Install CDK dependencies

```bash
cd cdk
npm install
```

### 2. Bootstrap CDK (first time only)

```bash
npx cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

### 3. Deploy

**Dev mode** (faster deploys, single task, reduced health check intervals):

```bash
npx cdk deploy -c env=dev --require-approval never
```

**Prod mode** (default — 2 tasks, auto-scaling, standard intervals):

```bash
npx cdk deploy --require-approval never
```

### 4. Set secrets (required after first deploy)

CDK creates two Secrets Manager secrets with placeholder values. You must set the real values manually after the stack deploys:

**OpenAI API key** (required for OpenAI provider):

```bash
aws secretsmanager put-secret-value \
  --secret-id gateway/openai-api-key \
  --secret-string "sk-your-openai-key-here" \
  --region <REGION>
```

**Gateway API key** (required for client authentication):

```bash
aws secretsmanager put-secret-value \
  --secret-id gateway/api-key \
  --secret-string "$(openssl rand -hex 32)" \
  --region <REGION>
```

Retrieve the generated gateway key for use in requests:

```bash
aws secretsmanager get-secret-value \
  --secret-id gateway/api-key \
  --region <REGION> \
  --query SecretString --output text
```

> **Important:** After setting secrets, force a new ECS deployment so the tasks pick up the new values:
> ```bash
> aws ecs update-service --cluster <cluster-name> --service <service-name> --force-new-deployment --region <REGION>
> ```

Both secrets have a RETAIN removal policy — they survive stack deletion and won't be overwritten on subsequent deploys.

### 5. Test the endpoint

```bash
curl -X POST https://<cloudfront-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-gateway-api-key>" \
  -d '{"model": "test", "messages": [{"role": "user", "content": "Hello"}]}'
```

Alternatively, use the `X-API-Key` header:

```bash
curl -X POST https://<cloudfront-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-gateway-api-key>" \
  -d '{"model": "test", "messages": [{"role": "user", "content": "Hello"}]}'
```

The `model` field in the request is ignored — the gateway routes to the configured Bedrock or OpenAI model based on health metrics.

## Authentication

The gateway validates requests using an API key stored in Secrets Manager (`gateway/api-key`). Clients must include the key in either:

- `Authorization: Bearer <key>` header
- `X-API-Key: <key>` header

The `/health` endpoint is exempt from authentication (used by ALB health checks).

If the `GATEWAY_API_KEY` environment variable is empty or not set, the gateway runs in open mode (no auth).

## Deploy Modes

| Setting | Dev (`-c env=dev`) | Prod (default) |
|---------|-------------------|----------------|
| Desired task count | 1 | 2 |
| Max task count | 2 | 6 |
| Health check interval | 10s | 30s |
| Deregistration delay | 10s | 300s |
| Auto-scaling | CPU-based | CPU-based |

## Configuration

All routing behavior is configurable via environment variables (set in the CDK stack):

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_LATENCY_THRESHOLD_MS` | 5000 | Latency (ms) above which a provider is unhealthy |
| `GATEWAY_ERROR_RATE_THRESHOLD` | 0.5 | Error rate (0-1) above which a provider is unhealthy |
| `GATEWAY_WINDOW_SIZE` | 50 | Sliding window size for health tracking |
| `GATEWAY_PRIMARY_PROVIDER` | bedrock | Primary provider preference (bedrock/openai) |
| `GATEWAY_BEDROCK_MODEL_ID` | us.anthropic.claude-haiku-4-5-20251001-v1:0 | Bedrock inference profile ID |
| `GATEWAY_BEDROCK_REGION` | us-east-2 | Bedrock API region |
| `GATEWAY_OPENAI_MODEL` | gpt-4o-mini | OpenAI model |
| `GATEWAY_REQUEST_TIMEOUT_SECONDS` | 30.0 | Request timeout per provider |

## Routing Algorithm

The routing engine uses a health score formula:

```
score = avg_latency_ms × (1 + error_rate)
```

Decision logic:
1. If one provider is healthy and the other unhealthy → pick the healthy one
2. If both healthy → pick the lower score (primary wins ties)
3. If both unhealthy → pick the lower error rate (primary wins ties)
4. On request failure → retry with the alternate provider before returning error

## CloudWatch Dashboard

A CloudWatch dashboard (`gateway-routing`) is created automatically with:

- Provider selection distribution over time
- Request latency comparison (Bedrock vs OpenAI)
- Health scores per provider
- Error rates per provider
- Failover event count
- Request volume

Metrics are emitted via CloudWatch Embedded Metric Format (EMF) — no extra API calls or metric filters needed.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions (sync + streaming) |
| `/health` | GET | Health check with per-provider status |

## Project Structure

```
├── cdk/                          # CDK infrastructure (TypeScript)
│   ├── bin/app.ts               # CDK app entry point
│   ├── lib/gateway-stack.ts     # Main stack
│   └── lib/constructs/          # Modular constructs
│       ├── network-construct.ts
│       ├── compute-construct.ts
│       ├── load-balancer-construct.ts
│       ├── distribution-construct.ts
│       ├── secrets-construct.ts
│       ├── observability-construct.ts
│       └── dashboard-construct.ts
├── gateway/                      # FastAPI application (Python)
│   ├── app.py                   # Main app with request handler + auth middleware
│   ├── routing.py               # Routing engine with health score algorithm
│   ├── health.py                # Health tracker (sliding window via deque)
│   ├── providers.py             # Provider clients (Bedrock invoke-model + OpenAI)
│   ├── config.py                # Configuration from env vars
│   ├── models.py                # Pydantic request/response models
│   ├── metrics.py               # CloudWatch EMF metric emission
│   ├── logging_config.py        # Structured JSON logging setup
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile               # Container image (python:3.12-slim + curl)
│   └── tests/                   # Unit tests
└── README.md
```

## Teardown

```bash
cd cdk
npx cdk destroy
```

Note: Secrets Manager secrets are retained after stack deletion (RETAIN policy). Delete them manually if needed:

```bash
aws secretsmanager delete-secret --secret-id gateway/openai-api-key --force-delete-without-recovery --region <REGION>
aws secretsmanager delete-secret --secret-id gateway/api-key --force-delete-without-recovery --region <REGION>
```

## Cost Estimate

Running in dev mode (~$2-3/day):
- 1 Fargate task (0.5 vCPU, 1GB)
- NAT Gateway
- ALB
- CloudFront distribution

Running in prod mode (~$4-6/day):
- 2 Fargate tasks (0.5 vCPU, 1GB each)
- NAT Gateway
- ALB
- CloudFront distribution

## License

See [LICENSE](LICENSE).
