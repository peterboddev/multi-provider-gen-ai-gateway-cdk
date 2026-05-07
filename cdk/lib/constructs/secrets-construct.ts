import * as cdk from 'aws-cdk-lib';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface SecretsConstructProps {
  openAiApiKeySecretName?: string; // default: "gateway/openai-api-key"
  gatewayApiKeySecretName?: string; // default: "gateway/api-key"
}

export class SecretsConstruct extends Construct {
  public readonly openAiSecret: secretsmanager.ISecret;
  public readonly gatewayApiKeySecret: secretsmanager.ISecret;
  public readonly ecsSecrets: Record<string, ecs.Secret>;

  constructor(scope: Construct, id: string, props?: SecretsConstructProps) {
    super(scope, id);

    const openAiSecretName = props?.openAiApiKeySecretName ?? 'gateway/openai-api-key';
    const gatewayApiKeySecretName = props?.gatewayApiKeySecretName ?? 'gateway/api-key';

    // OpenAI API key secret
    const openAiSecret = new secretsmanager.Secret(this, 'OpenAiApiKey', {
      secretName: openAiSecretName,
      description: 'OpenAI API key for the multi-provider gateway. Set value manually after deploy.',
    });
    openAiSecret.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    this.openAiSecret = openAiSecret;

    // Gateway API key secret (for authenticating client requests)
    // CDK creates the shell. Set the real value manually after deploy:
    //   aws secretsmanager put-secret-value --secret-id gateway/api-key --secret-string "$(openssl rand -hex 32)"
    const gatewayApiKey = new secretsmanager.Secret(this, 'GatewayApiKey', {
      secretName: gatewayApiKeySecretName,
      description: 'API key for authenticating requests to the gateway. Set value manually after deploy.',
    });
    gatewayApiKey.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    this.gatewayApiKeySecret = gatewayApiKey;

    // ECS-compatible secret mapping for container injection
    this.ecsSecrets = {
      OPENAI_API_KEY: ecs.Secret.fromSecretsManager(this.openAiSecret),
      GATEWAY_API_KEY: ecs.Secret.fromSecretsManager(this.gatewayApiKeySecret),
    };
  }
}
