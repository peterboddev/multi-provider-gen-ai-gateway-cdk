import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface SecretsConstructProps {
  openAiApiKeySecretName?: string; // default: "gateway/openai-api-key"
}

export class SecretsConstruct extends Construct {
  public readonly openAiSecret: secretsmanager.ISecret;
  public readonly ecsSecrets: Record<string, ecs.Secret>;

  constructor(scope: Construct, id: string, props?: SecretsConstructProps) {
    super(scope, id);

    const secretName = props?.openAiApiKeySecretName ?? 'gateway/openai-api-key';

    this.openAiSecret = new secretsmanager.Secret(this, 'OpenAiApiKey', {
      secretName,
      description: 'OpenAI API key for the multi-provider gateway',
    });

    // ECS-compatible secret mapping for container injection
    this.ecsSecrets = {
      OPENAI_API_KEY: ecs.Secret.fromSecretsManager(this.openAiSecret),
    };
  }
}
