import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';

export interface DistributionConstructProps {
  alb: elbv2.ApplicationLoadBalancer;
  originSecret?: string; // shared secret for ALB origin verification
}

export class DistributionConstruct extends Construct {
  public readonly distribution: cloudfront.Distribution;
  public readonly distributionUrl: string;

  constructor(scope: Construct, id: string, props: DistributionConstructProps) {
    super(scope, id);

    const originSecret = props.originSecret ?? 'gateway-origin-verify-secret';

    // Create the ALB origin with custom header for verification.
    // ALB only exposes HTTP (port 80); CloudFront handles HTTPS at the edge.
    const albOrigin = new origins.HttpOrigin(props.alb.loadBalancerDnsName, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      customHeaders: {
        'X-Origin-Verify': originSecret,
      },
    });

    // Use the managed CACHING_DISABLED policy — CloudFront does not allow
    // HeaderBehavior on custom policies when caching is disabled (all TTLs = 0).
    const apiCachePolicy = cloudfront.CachePolicy.CACHING_DISABLED;

    // Origin request policy to forward relevant headers and query strings to the ALB.
    // Using ALL_VIEWER_EXCEPT_HOST_HEADER forwards all headers (including Authorization
    // and Content-Type) plus query strings to the origin.
    const originRequestPolicy = cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER;

    // CloudFront distribution — terminates HTTPS from clients, forwards to ALB over HTTP
    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultBehavior: {
        origin: albOrigin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: apiCachePolicy,
        originRequestPolicy: originRequestPolicy,
      },
      comment: 'Multi-Provider Gen AI Gateway',
    });

    this.distributionUrl = `https://${this.distribution.distributionDomainName}`;
  }
}
