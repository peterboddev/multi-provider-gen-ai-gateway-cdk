import * as cdk from 'aws-cdk-lib';
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

    // Cache policy that disables caching for API traffic.
    // POST requests are never cached by CloudFront by default, but we also
    // set TTLs to 0 so GET/OPTIONS responses are not cached either.
    const apiCachePolicy = new cloudfront.CachePolicy(this, 'ApiCachePolicy', {
      cachePolicyName: `GatewayApiNoCachePolicy-${cdk.Names.uniqueId(this)}`,
      defaultTtl: cdk.Duration.seconds(0),
      minTtl: cdk.Duration.seconds(0),
      maxTtl: cdk.Duration.seconds(0),
      headerBehavior: cloudfront.CacheHeaderBehavior.allowList(
        'Authorization',
        'Content-Type',
      ),
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.all(),
      enableAcceptEncodingGzip: true,
    });

    // Origin request policy to forward relevant headers to the ALB.
    // Note: Authorization is forwarded via the CachePolicy above (CloudFront
    // does not allow Authorization in OriginRequestPolicy).
    const originRequestPolicy = new cloudfront.OriginRequestPolicy(this, 'OriginRequestPolicy', {
      originRequestPolicyName: `GatewayOriginRequestPolicy-${cdk.Names.uniqueId(this)}`,
      headerBehavior: cloudfront.OriginRequestHeaderBehavior.allowList(
        'Content-Type',
      ),
      queryStringBehavior: cloudfront.OriginRequestQueryStringBehavior.all(),
    });

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
