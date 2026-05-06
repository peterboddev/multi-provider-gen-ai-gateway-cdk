import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';

export interface LoadBalancerConstructProps {
  vpc: ec2.IVpc;
  healthCheckPath?: string; // default: "/health"
}

export class LoadBalancerConstruct extends Construct {
  public readonly alb: elbv2.ApplicationLoadBalancer;
  public readonly targetGroup: elbv2.ApplicationTargetGroup;
  public readonly listener: elbv2.ApplicationListener;
  public readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: LoadBalancerConstructProps) {
    super(scope, id);

    // Security group for ALB
    // Security is enforced via custom origin header validation,
    // matching the pattern used in the original Terraform project.
    this.albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc: props.vpc,
      description: 'Security group for the gateway ALB',
      allowAllOutbound: true,
    });

    // Allow inbound HTTP from anywhere — CloudFront connects over HTTP to the ALB.
    // Actual access restriction is handled by custom origin header verification.
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP traffic (CloudFront origin connection)'
    );

    // Create ALB in public subnets
    this.alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc: props.vpc,
      internetFacing: true,
      securityGroup: this.albSecurityGroup,
    });

    // Create target group with health check on /health
    this.targetGroup = new elbv2.ApplicationTargetGroup(this, 'TargetGroup', {
      vpc: props.vpc,
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: props.healthCheckPath ?? '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    // Create HTTP listener — CloudFront handles HTTPS termination at the edge
    this.listener = this.alb.addListener('HttpListener', {
      port: 80,
      defaultTargetGroups: [this.targetGroup],
    });
  }
}
