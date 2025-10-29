/**
 * API routes for service management
 */
import { Router, Request, Response } from 'express';
import { ServiceDiscovery } from '../services/ServiceDiscovery';
import { SpecAggregator } from '../services/SpecAggregator';
import logger from '../utils/logger';

export function createApiRoutes(discovery: ServiceDiscovery, aggregator: SpecAggregator): Router {
  const router = Router();

  /**
   * GET /api/services
   * Get list of all registered services with their status
   */
  router.get('/services', (_req: Request, res: Response) => {
    const statuses = discovery.getAllServiceStatuses();

    res.json({
      timestamp: new Date(),
      count: statuses.length,
      services: statuses,
    });
  });

  /**
   * GET /api/services/:name
   * Get details for a specific service
   */
  router.get('/services/:name', (req: Request, res: Response) => {
    const serviceName = req.params.name;
    const status = discovery.getServiceStatus(serviceName);

    if (!status) {
      res.status(404).json({
        error: `Service not found: ${serviceName}`,
      });
      return;
    }

    res.json(status);
  });

  /**
   * GET /api/specs
   * Get aggregated OpenAPI specification
   */
  router.get('/specs', async (_req: Request, res: Response) => {
    try {
      // Try to use cached specs first
      let cachedSpecs = discovery.getAllCachedSpecs();

      // If no cached specs, fetch them
      if (cachedSpecs.length === 0) {
        logger.info('No cached specs found, fetching from services');
        cachedSpecs = await discovery.fetchAllServiceSpecs();
      }

      const aggregatedSpec = aggregator.mergeSpecs(cachedSpecs);

      res.json(aggregatedSpec);
    } catch (error) {
      logger.error(`Failed to get aggregated specs: ${error}`);
      res.status(500).json({
        error: 'Failed to aggregate specifications',
      });
    }
  });

  /**
   * GET /api/specs/:service
   * Get OpenAPI specification for a specific service
   */
  router.get('/specs/:service', async (req: Request, res: Response) => {
    try {
      const serviceName = req.params.service;
      const service = discovery.getService(serviceName);

      if (!service) {
        res.status(404).json({
          error: `Service not found: ${serviceName}`,
        });
        return;
      }

      // Try cached spec first
      let spec = discovery.getCachedSpec(serviceName);

      // If not cached, fetch it
      if (!spec) {
        const fetchedSpec = await discovery.fetchServiceSpec(service);
        spec = fetchedSpec || undefined;
      }

      if (!spec) {
        res.status(503).json({
          error: `Failed to fetch specification for service: ${serviceName}`,
        });
        return;
      }

      res.json(spec);
    } catch (error) {
      logger.error(`Failed to get service spec: ${error}`);
      res.status(500).json({
        error: 'Failed to fetch service specification',
      });
    }
  });

  /**
   * POST /api/refresh
   * Force refresh of service specifications and health
   */
  router.post('/refresh', async (_req: Request, res: Response) => {
    try {
      logger.info('Manual refresh triggered');

      // Clear caches
      discovery.clearCaches();

      // Fetch fresh data
      const [specs, health] = await Promise.all([
        discovery.fetchAllServiceSpecs(),
        discovery.checkAllServicesHealth(),
      ]);

      res.json({
        message: 'Refresh completed',
        timestamp: new Date(),
        services: {
          total: discovery.getServices().length,
          specsFound: specs.length,
          healthyServices: health.filter((h) => h.status === 'healthy').length,
        },
      });
    } catch (error) {
      logger.error(`Refresh failed: ${error}`);
      res.status(500).json({
        error: 'Failed to refresh services',
      });
    }
  });

  /**
   * POST /api/refresh/:service
   * Refresh a specific service
   */
  router.post('/refresh/:service', async (req: Request, res: Response) => {
    try {
      const serviceName = req.params.service;
      const service = discovery.getService(serviceName);

      if (!service) {
        res.status(404).json({
          error: `Service not found: ${serviceName}`,
        });
        return;
      }

      logger.info(`Manual refresh triggered for ${serviceName}`);

      // Clear cache for this service
      discovery.clearServiceCache(serviceName);

      // Fetch fresh data
      const [spec, health] = await Promise.all([
        discovery.fetchServiceSpec(service),
        discovery.checkServiceHealth(service),
      ]);

      res.json({
        message: `Refresh completed for ${serviceName}`,
        timestamp: new Date(),
        service: {
          name: serviceName,
          specAvailable: spec !== null,
          health: health.status,
        },
      });
    } catch (error) {
      logger.error(`Refresh failed for service: ${error}`);
      res.status(500).json({
        error: 'Failed to refresh service',
      });
    }
  });

  /**
   * GET /api/status
   * Get comprehensive system status
   */
  router.get('/status', (_req: Request, res: Response) => {
    const services = discovery.getAllServiceStatuses();
    const healthyCount = services.filter((s) => s.health.status === 'healthy').length;
    const specsCount = services.filter((s) => s.specAvailable).length;

    res.json({
      timestamp: new Date(),
      aggregator: {
        name: 'Swagger Aggregator Service',
        version: '1.0.0',
        status: 'running',
      },
      services: {
        total: services.length,
        healthy: healthyCount,
        unhealthy: services.length - healthyCount,
        specsAvailable: specsCount,
      },
      details: services,
    });
  });

  return router;
}
