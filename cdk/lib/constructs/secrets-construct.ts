import * as cdk from 'aws-cdk-lib';
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

    // Create the secret shell. CDK generates a placeholder value on first deploy.
    // Set the real value manually after deploy:
    //   aws secretsmanager put-secret-value --secret-id gateway/openai-api-key --secret-string "sk-..."
    // RETAIN policy ensures the secret (and its value) survives stack deletion.
    const secret = new secretsmanager.Secret(this, 'OpenAiApiKey', {
      secretName,
      description: 'OpenAI API key for the multi-provider gateway. Set value manually after deploy.',
    });
    secret.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);

    this.openAiSecret = secret;

    // ECS-compatible secret mapping for container injection
    this.ecsSecrets = {
      OPENAI_API_KEY: ecs.Secret.fromSecretsManager(this.openAiSecret),
    };
  }
}
