import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { Construct } from 'constructs';

export interface DashboardConstructProps {
  serviceName: string;
}

export class DashboardConstruct extends Construct {
  public readonly dashboard: cloudwatch.Dashboard;

  constructor(scope: Construct, id: string, props: DashboardConstructProps) {
    super(scope, id);

    const namespace = 'Gateway';

    this.dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: `${props.serviceName}-routing`,
    });

    // Row 1: Provider Selection & Routing Reasons
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Provider Selection (requests/min)',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'ProviderSelected',
            dimensionsMap: { Provider: 'bedrock', Reason: 'lower_score_or_primary_tie' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'ProviderSelected',
            dimensionsMap: { Provider: 'openai', Reason: 'lower_score' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI',
            color: '#10A37F',
          }),
        ],
      }),
      new cloudwatch.GraphWidget({
        title: 'Failover Events',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'FailoverCount',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'Failover to Bedrock',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'FailoverCount',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'Failover to OpenAI',
            color: '#10A37F',
          }),
        ],
      }),
    );

    // Row 2: Latency Comparison & Health Scores
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Request Latency by Provider (ms)',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'RequestLatency',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Avg Latency',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'RequestLatency',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Avg Latency',
            color: '#10A37F',
          }),
        ],
      }),
      new cloudwatch.GraphWidget({
        title: 'Health Scores (lower = healthier)',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'HealthScore',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Score',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'HealthScore',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Score',
            color: '#10A37F',
          }),
        ],
      }),
    );

    // Row 3: Error Rates & Request Volume
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Error Rate by Provider',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'ErrorRate',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Error Rate',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'ErrorRate',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Error Rate',
            color: '#10A37F',
          }),
        ],
        leftYAxis: { min: 0, max: 1 },
      }),
      new cloudwatch.GraphWidget({
        title: 'Request Volume by Provider',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'RequestCount',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Requests',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'RequestCount',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Requests',
            color: '#10A37F',
          }),
        ],
      }),
    );

    // Row 4: Rolling Average Latency (from health tracker)
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Rolling Avg Latency (Health Tracker Window)',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'AvgLatency',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Rolling Avg',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'AvgLatency',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Average',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Rolling Avg',
            color: '#10A37F',
          }),
        ],
      }),
      new cloudwatch.GraphWidget({
        title: 'Error Count by Provider',
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace,
            metricName: 'ErrorCount',
            dimensionsMap: { Provider: 'bedrock' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'Bedrock Errors',
            color: '#FF9900',
          }),
          new cloudwatch.Metric({
            namespace,
            metricName: 'ErrorCount',
            dimensionsMap: { Provider: 'openai' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
            label: 'OpenAI Errors',
            color: '#10A37F',
          }),
        ],
      }),
    );
  }
}
