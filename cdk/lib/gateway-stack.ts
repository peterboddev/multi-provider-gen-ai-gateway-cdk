import * as cdk from 'aws-cdk-lib';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as path from 'path';
import { Construct } from 'constructs';
import { NetworkConstruct } from './constructs/network-construct';
import { SecretsConstruct } from './constructs/secrets-construct';
import { LoadBalancerConstruct } from './constructs/load-balancer-construct';
import { ComputeConstruct } from './constructs/compute-construct';
import { DistributionConstruct } from './constructs/distribution-construct';
import { ObservabilityConstruct } from './constructs/observability-construct';

export interface GatewayStackProps extends cdk.StackProps {
  taskCpu?: number;
  taskMemory?: number;
  desiredCount?: number;
  maxCount?: number;
  latencyThresholdMs?: number;
  errorRateThreshold?: number;
  windowSize?: number;
  primaryProvider?: string;
  bedrockModelId?: string;
  bedrockRegion?: string;
  openaiModel?: string;
}

export class GatewayStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: GatewayStackProps) {
    super(scope, id, props);

    // 1. Network
    const network = new NetworkConstruct(this, 'Network');

    // 2. Secrets
    const secrets = new SecretsConstruct(this, 'Secrets');

    // 3. Load Balancer
    const loadBalancer = new LoadBalancerConstruct(this, 'LoadBalancer', {
      vpc: network.vpc,
    });

    // 4. Observability (needs target group for alarm)
    const observability = new ObservabilityConstruct(this, 'Observability', {
      serviceName: 'gateway',
      targetGroup: loadBalancer.targetGroup,
    });

    // 5. Compute
    const compute = new ComputeConstruct(this, 'Compute', {
      vpc: network.vpc,
      taskCpu: props?.taskCpu,
      taskMemory: props?.taskMemory,
      desiredCount: props?.desiredCount,
      maxCount: props?.maxCount,
      containerImage: ecs.ContainerImage.fromAsset(path.join(__dirname, '../../gateway')),
      secrets: secrets.ecsSecrets,
      environment: {
        GATEWAY_LATENCY_THRESHOLD_MS: String(props?.latencyThresholdMs ?? 5000),
        GATEWAY_ERROR_RATE_THRESHOLD: String(props?.errorRateThreshold ?? 0.5),
        GATEWAY_WINDOW_SIZE: String(props?.windowSize ?? 50),
        GATEWAY_PRIMARY_PROVIDER: props?.primaryProvider ?? 'bedrock',
        GATEWAY_BEDROCK_MODEL_ID: props?.bedrockModelId ?? 'anthropic.claude-3-sonnet-20240229-v1:0',
        GATEWAY_BEDROCK_REGION: props?.bedrockRegion ?? 'us-east-1',
        GATEWAY_OPENAI_MODEL: props?.openaiModel ?? 'gpt-4o',
      },
      targetGroup: loadBalancer.targetGroup,
      logGroup: observability.logGroup,
    });

    // 6. CloudFront Distribution
    const distribution = new DistributionConstruct(this, 'Distribution', {
      alb: loadBalancer.alb,
    });

    // Stack outputs
    new cdk.CfnOutput(this, 'CloudFrontUrl', {
      value: distribution.distributionUrl,
      description: 'CloudFront distribution URL',
    });

    new cdk.CfnOutput(this, 'AlbDnsName', {
      value: loadBalancer.alb.loadBalancerDnsName,
      description: 'ALB DNS name',
    });
  }
}
