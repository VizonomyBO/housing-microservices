/**
 * Environment configuration
 */
import dotenv from 'dotenv';

dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || '3000', 10),
  nodeEnv: process.env.NODE_ENV || 'development',
  logLevel: process.env.LOG_LEVEL || 'info',

  // Service URLs
  accountServiceUrl: process.env.ACCOUNT_SERVICE_URL || 'http://localhost:5001',
  userServiceUrl: process.env.USER_SERVICE_URL || 'http://localhost:5002',
  documentServiceUrl: process.env.DOCUMENT_SERVICE_URL || 'https://z1xfknvwo3.execute-api.us-east-1.amazonaws.com/dev',

  // Refresh intervals (in milliseconds)
  specRefreshInterval: parseInt(process.env.SPEC_REFRESH_INTERVAL || '300000', 10), // 5 minutes
  healthCheckInterval: parseInt(process.env.HEALTH_CHECK_INTERVAL || '60000', 10), // 1 minute

  // Timeouts (in milliseconds)
  httpTimeout: parseInt(process.env.HTTP_TIMEOUT || '5000', 10),

  // CORS
  corsOrigins: process.env.CORS_ORIGINS?.split(',') || ['*'],

  // Application metadata
  appName: 'Swagger Aggregator Service',
  appVersion: '1.0.0',
  appDescription: 'Centralized API documentation portal for microservices',
};

export default config;
