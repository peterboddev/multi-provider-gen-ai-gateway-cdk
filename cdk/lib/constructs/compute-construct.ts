import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface ComputeConstructProps {
  vpc: ec2.IVpc;
  taskCpu?: number; // default: 512
  taskMemory?: number; // default: 1024
  desiredCount?: number; // default: 2
  maxCount?: number; // default: 6
  containerImage: ecs.ContainerImage;
  secrets: Record<string, ecs.Secret>;
  environment: Record<string, string>;
  targetGroup: elbv2.ApplicationTargetGroup;
  logGroup: logs.ILogGroup;
}

export class ComputeConstruct extends Construct {
  public readonly cluster: ecs.Cluster;
  public readonly service: ecs.FargateService;
  public readonly taskDefinition: ecs.FargateTaskDefinition;

  constructor(scope: Construct, id: string, props: ComputeConstructProps) {
    super(scope, id);

    // ECS Cluster
    this.cluster = new ecs.Cluster(this, 'Cluster', {
      vpc: props.vpc,
    });

    // Fargate Task Definition
    this.taskDefinition = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      cpu: props.taskCpu ?? 512,
      memoryLimitMiB: props.taskMemory ?? 1024,
    });

    // Grant Bedrock invoke permissions to the task role
    this.taskDefinition.taskRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'bedrock-mantle:*',
        ],
        resources: ['*'],
      })
    );

    // Add container to task definition
    const container = this.taskDefinition.addContainer('GatewayContainer', {
      image: props.containerImage,
      logging: ecs.LogDrivers.awsLogs({
        logGroup: props.logGroup,
        streamPrefix: 'gateway',
      }),
      secrets: props.secrets,
      environment: props.environment,
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8000/health || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    container.addPortMappings({
      containerPort: 8000,
      protocol: ecs.Protocol.TCP,
    });

    // Fargate Service in private subnets
    this.service = new ecs.FargateService(this, 'Service', {
      cluster: this.cluster,
      taskDefinition: this.taskDefinition,
      desiredCount: props.desiredCount ?? 2,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      assignPublicIp: false,
    });

    // Attach to ALB target group
    this.service.attachToApplicationTargetGroup(props.targetGroup);

    // Auto-scaling based on CPU utilization
    const scaling = this.service.autoScaleTaskCount({
      minCapacity: props.desiredCount ?? 2,
      maxCapacity: props.maxCount ?? 6,
    });

    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });
  }
}
