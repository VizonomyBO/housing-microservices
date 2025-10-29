/**
 * Health check and monitoring types
 */

export interface HealthCheckResult {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: Date;
  services: {
    [serviceName: string]: {
      status: 'up' | 'down' | 'unknown';
      responseTime?: number;
      error?: string;
    };
  };
  aggregator: {
    uptime: number;
    version: string;
    memory: {
      used: number;
      total: number;
      percentage: number;
    };
  };
}

export interface ServiceHealthMetrics {
  serviceName: string;
  checks: number;
  successRate: number;
  averageResponseTime: number;
  lastSuccess?: Date;
  lastFailure?: Date;
}
