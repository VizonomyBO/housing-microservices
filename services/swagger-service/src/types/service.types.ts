/**
 * Service configuration and metadata types
 */

export interface ServiceConfig {
  name: string;
  url: string;
  specEndpoint: string;
  healthEndpoint: string;
  description: string;
  version?: string;
  tags?: string[];
  enabled?: boolean;
  /** Path to static OpenAPI spec file (for Lambda/serverless services) */
  staticSpecPath?: string;
  /** If true, skip health checks (for serverless services) */
  skipHealthCheck?: boolean;
}

export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'unhealthy' | 'unknown';
  responseTime?: number;
  lastChecked: Date;
  error?: string;
  metadata?: {
    version?: string;
    uptime?: number;
    [key: string]: unknown;
  };
}

export interface ServiceRegistry {
  services: ServiceConfig[];
  lastUpdated: Date;
}

export interface ServiceStatus {
  config: ServiceConfig;
  health: ServiceHealth;
  specAvailable: boolean;
}
