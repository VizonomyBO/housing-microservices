/**
 * Health monitoring service
 */
import { HealthCheckResult, ServiceHealthMetrics } from '../types/health.types';
import { ServiceDiscovery } from './ServiceDiscovery';
import { getUptime, getMemoryUsage } from '../utils/helpers';
import logger from '../utils/logger';
import config from '../config/environment';

export class HealthMonitor {
  private discovery: ServiceDiscovery;
  private intervalId?: NodeJS.Timeout;
  private metrics: Map<string, ServiceHealthMetrics>;

  constructor(discovery: ServiceDiscovery) {
    this.discovery = discovery;
    this.metrics = new Map();
  }

  /**
   * Start periodic health monitoring
   */
  start(): void {
    if (this.intervalId) {
      logger.warn('Health monitor already running');
      return;
    }

    logger.info(`Starting health monitor (interval: ${config.healthCheckInterval}ms)`);

    // Run initial check
    this.runHealthCheck();

    // Schedule periodic checks
    this.intervalId = setInterval(() => {
      this.runHealthCheck();
    }, config.healthCheckInterval);
  }

  /**
   * Stop health monitoring
   */
  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = undefined;
      logger.info('Stopped health monitor');
    }
  }

  /**
   * Run health check for all services
   */
  private async runHealthCheck(): Promise<void> {
    try {
      const healthResults = await this.discovery.checkAllServicesHealth();

      // Update metrics
      for (const health of healthResults) {
        this.updateMetrics(health.name, health.status === 'healthy', health.responseTime);
      }

      const healthyCount = healthResults.filter((h) => h.status === 'healthy').length;
      logger.info(
        `Health check complete: ${healthyCount}/${healthResults.length} services healthy`
      );
    } catch (error) {
      logger.error(`Health check failed: ${error}`);
    }
  }

  /**
   * Update metrics for a service
   */
  private updateMetrics(serviceName: string, success: boolean, responseTime?: number): void {
    const existing = this.metrics.get(serviceName);

    if (!existing) {
      this.metrics.set(serviceName, {
        serviceName,
        checks: 1,
        successRate: success ? 100 : 0,
        averageResponseTime: responseTime || 0,
        lastSuccess: success ? new Date() : undefined,
        lastFailure: success ? undefined : new Date(),
      });
      return;
    }

    const totalChecks = existing.checks + 1;
    const successCount =
      Math.round((existing.successRate / 100) * existing.checks) + (success ? 1 : 0);
    const newSuccessRate = (successCount / totalChecks) * 100;

    const newAvgResponseTime = responseTime
      ? (existing.averageResponseTime * existing.checks + responseTime) / totalChecks
      : existing.averageResponseTime;

    this.metrics.set(serviceName, {
      serviceName,
      checks: totalChecks,
      successRate: newSuccessRate,
      averageResponseTime: newAvgResponseTime,
      lastSuccess: success ? new Date() : existing.lastSuccess,
      lastFailure: success ? existing.lastFailure : new Date(),
    });
  }

  /**
   * Get current health status
   */
  async getCurrentHealth(): Promise<HealthCheckResult> {
    const healthStatuses = this.discovery.getAllCachedHealth();
    const services: HealthCheckResult['services'] = {};

    for (const health of healthStatuses) {
      services[health.name] = {
        status: health.status === 'healthy' ? 'up' : 'down',
        responseTime: health.responseTime,
        error: health.error,
      };
    }

    // Determine overall status
    const healthyCount = healthStatuses.filter((h) => h.status === 'healthy').length;
    const totalCount = healthStatuses.length;

    let status: 'healthy' | 'degraded' | 'unhealthy';
    if (healthyCount === totalCount) {
      status = 'healthy';
    } else if (healthyCount > 0) {
      status = 'degraded';
    } else {
      status = 'unhealthy';
    }

    return {
      status,
      timestamp: new Date(),
      services,
      aggregator: {
        uptime: getUptime(),
        version: config.appVersion,
        memory: getMemoryUsage(),
      },
    };
  }

  /**
   * Get metrics for a specific service
   */
  getServiceMetrics(serviceName: string): ServiceHealthMetrics | undefined {
    return this.metrics.get(serviceName);
  }

  /**
   * Get metrics for all services
   */
  getAllMetrics(): ServiceHealthMetrics[] {
    return Array.from(this.metrics.values());
  }

  /**
   * Reset metrics for a service
   */
  resetServiceMetrics(serviceName: string): void {
    this.metrics.delete(serviceName);
    logger.info(`Reset metrics for ${serviceName}`);
  }

  /**
   * Reset all metrics
   */
  resetAllMetrics(): void {
    this.metrics.clear();
    logger.info('Reset all metrics');
  }
}
