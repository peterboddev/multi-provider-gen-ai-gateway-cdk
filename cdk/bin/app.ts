#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { GatewayStack } from '../lib/gateway-stack';

const app = new cdk.App();

new GatewayStack(app, 'GatewayStack', {
  description: 'Multi-Provider Gen AI Gateway - CDK Infrastructure Stack',
});
