# Multi-Provider Gen AI Gateway (CDK)

A slim, CDK-based multi-provider LLM gateway with latency-based routing and automatic failover between AWS Bedrock and OpenAI.

## Architecture

```
Client → CloudFront → ALB → ECS Fargate (FastAPI)
                                   ├── Bedrock (OpenAI-compatible API)
                                   └── OpenAI
```

The FastAPI app tracks latency/errors per provider and routes to the healthier one. If one provider exceeds a latency threshold or error rate, traffic shifts to the other automatically.

## What's Included

- **CDK (TypeScript)** infrastructure — VPC, ECS Fargate, ALB, CloudFront, Secrets Manager, CloudWatch
- **FastAPI (Python)** application — OpenAI-compatible `/v1/chat/completions` endpoint
- **Latency-based routing** with sliding window health tracking
- **Automatic failover** between Bedrock and OpenAI
- **Structured JSON logging** with routing decision visibility

## What's NOT Included

No LiteLLM, no Redis, no RDS, no EKS, no admin UI, no chat history, no Okta auth.

## Prerequisites

- AWS account with Bedrock model access enabled
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

### 4. Set the OpenAI API key

After deployment, set the secret value:

```bash
aws secretsmanager put-secret-value \
  --secret-id gateway/openai-api-key \
  --secret-string "sk-your-key-here" \
  --region <REGION>
```

### 5. Test the endpoint

```bash
curl -X POST https://<cloudfront-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Summarize this document..."}]}'
```

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
| `GATEWAY_BEDROCK_MODEL_ID` | us.anthropic.claude-3-5-sonnet-20241022-v2:0 | Bedrock model ID |
| `GATEWAY_BEDROCK_REGION` | us-east-1 | Bedrock API region |
| `GATEWAY_OPENAI_MODEL` | gpt-4o | OpenAI model |
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
│       └── observability-construct.ts
├── gateway/                      # FastAPI application (Python)
│   ├── app.py                   # Main app with request handler
│   ├── routing.py               # Routing engine
│   ├── health.py                # Health tracker (sliding window)
│   ├── providers.py             # Provider client (Bedrock + OpenAI)
│   ├── config.py                # Configuration from env vars
│   ├── models.py                # Pydantic models
│   ├── Dockerfile               # Container image
│   └── tests/                   # Unit tests
└── README.md
```

## Teardown

```bash
cd cdk
npx cdk destroy
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
