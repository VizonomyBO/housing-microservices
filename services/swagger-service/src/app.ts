/**
 * Main application entry point
 */
import express, { Express } from 'express';
import { ServiceDiscovery } from './services/ServiceDiscovery';
import { SpecAggregator } from './services/SpecAggregator';
import { HealthMonitor } from './services/HealthMonitor';
import { createHealthRoutes } from './routes/health.routes';
import { createApiRoutes } from './routes/api.routes';
import { createDocsRoutes } from './routes/docs.routes';
import { corsMiddleware } from './middleware/cors.middleware';
import { loggingMiddleware } from './middleware/logging.middleware';
import { errorHandler, notFoundHandler } from './middleware/error.middleware';
import logger from './utils/logger';
import config from './config/environment';
import services from './config/services';

/**
 * Create and configure Express application
 */
function createApp(): Express {
  const app = express();

  // Initialize services
  const discovery = new ServiceDiscovery(services);
  const aggregator = new SpecAggregator();
  const healthMonitor = new HealthMonitor(discovery);

  // Middleware
  app.use(corsMiddleware);
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use(loggingMiddleware);

  // Routes - docs routes must come first to handle /docs before notFoundHandler
  app.use('/', createHealthRoutes(healthMonitor));
  app.use('/api', createApiRoutes(discovery, aggregator));
  app.use('/', createDocsRoutes(discovery, aggregator));

  // Error handling
  app.use(notFoundHandler);
  app.use(errorHandler);

  // Initialize health monitoring
  healthMonitor.start();

  // Fetch initial specs
  discovery
    .fetchAllServiceSpecs()
    .then((specs) => {
      logger.info(`Initial spec fetch completed: ${specs.length} services`);
    })
    .catch((error) => {
      logger.error(`Initial spec fetch failed: ${error}`);
    });

  // Check initial health
  discovery
    .checkAllServicesHealth()
    .then((health) => {
      const healthyCount = health.filter((h) => h.status === 'healthy').length;
      logger.info(`Initial health check: ${healthyCount}/${health.length} services healthy`);
    })
    .catch((error) => {
      logger.error(`Initial health check failed: ${error}`);
    });

  // Periodic spec refresh
  setInterval(() => {
    logger.info('Refreshing service specifications');
    discovery.fetchAllServiceSpecs().catch((error) => {
      logger.error(`Spec refresh failed: ${error}`);
    });
  }, config.specRefreshInterval);

  // Graceful shutdown
  process.on('SIGTERM', () => {
    logger.info('SIGTERM received, shutting down gracefully');
    healthMonitor.stop();
    process.exit(0);
  });

  process.on('SIGINT', () => {
    logger.info('SIGINT received, shutting down gracefully');
    healthMonitor.stop();
    process.exit(0);
  });

  return app;
}

/**
 * Start the server
 */
function startServer(): void {
  const app = createApp();

  app.listen(config.port, () => {
    logger.info(`
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   Swagger Aggregator Service                             ║
║   Version: ${config.appVersion}                                     ║
║                                                           ║
║   Server running on: http://localhost:${config.port}              ║
║   Environment: ${config.nodeEnv}                             ║
║                                                           ║
║   Endpoints:                                              ║
║   - Documentation:  http://localhost:${config.port}/docs          ║
║   - Health Check:   http://localhost:${config.port}/health        ║
║   - API Status:     http://localhost:${config.port}/api/status    ║
║   - Service List:   http://localhost:${config.port}/api/services  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    `);
  });
}

// Start the server
startServer();

export { createApp };
