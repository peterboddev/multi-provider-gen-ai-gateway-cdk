import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface ObservabilityConstructProps {
  serviceName: string;
  targetGroup: elbv2.ApplicationTargetGroup;
  errorRateAlarmThreshold?: number; // default: 5 (percent)
}

export class ObservabilityConstruct extends Construct {
  public readonly logGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: ObservabilityConstructProps) {
    super(scope, id);

    // CloudWatch Log Group for ECS tasks
    this.logGroup = new logs.LogGroup(this, 'LogGroup', {
      logGroupName: `/ecs/${props.serviceName}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // CloudWatch Alarm for elevated error rates on the ALB target group
    const httpErrorMetric = props.targetGroup.metrics.httpCodeTarget(
      elbv2.HttpCodeTarget.TARGET_5XX_COUNT,
      {
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      }
    );

    new cloudwatch.Alarm(this, 'HighErrorRateAlarm', {
      alarmName: `${props.serviceName}-high-error-rate`,
      alarmDescription: `Alarm when ${props.serviceName} target group 5xx error rate exceeds threshold`,
      metric: httpErrorMetric,
      threshold: props.errorRateAlarmThreshold ?? 5,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
  }
}
