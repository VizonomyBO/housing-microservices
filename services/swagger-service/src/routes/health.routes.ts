/**
 * Health check routes
 */
import { Router, Request, Response } from 'express';
import { HealthMonitor } from '../services/HealthMonitor';

export function createHealthRoutes(healthMonitor: HealthMonitor): Router {
  const router = Router();

  /**
   * GET /health
   * Basic health check endpoint
   */
  router.get('/health', async (_req: Request, res: Response) => {
    try {
      const health = await healthMonitor.getCurrentHealth();
      const statusCode = health.status === 'healthy' ? 200 : 503;

      res.status(statusCode).json(health);
    } catch (error) {
      res.status(500).json({
        status: 'unhealthy',
        error: 'Failed to check health',
        timestamp: new Date(),
      });
    }
  });

  /**
   * GET /health/metrics
   * Detailed health metrics
   */
  router.get('/health/metrics', (_req: Request, res: Response) => {
    const metrics = healthMonitor.getAllMetrics();

    res.json({
      timestamp: new Date(),
      metrics,
    });
  });

  /**
   * GET /health/metrics/:service
   * Metrics for a specific service
   */
  router.get('/health/metrics/:service', (req: Request, res: Response) => {
    const serviceName = req.params.service;
    const metrics = healthMonitor.getServiceMetrics(serviceName);

    if (!metrics) {
      res.status(404).json({
        error: `No metrics found for service: ${serviceName}`,
      });
      return;
    }

    res.json(metrics);
  });

  return router;
}
