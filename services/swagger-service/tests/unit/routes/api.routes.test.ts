/**
 * Unit tests for API routes
 */
import request from 'supertest';
import express, { Express } from 'express';
import { createApiRoutes } from '../../../src/routes/api.routes';
import { ServiceDiscovery } from '../../../src/services/ServiceDiscovery';
import { SpecAggregator } from '../../../src/services/SpecAggregator';
import { ServiceConfig, ServiceHealth, ServiceStatus } from '../../../src/types/service.types';
import logger from '../../../src/utils/logger';

jest.mock('../../../src/services/ServiceDiscovery');
jest.mock('../../../src/services/SpecAggregator');
jest.mock('../../../src/utils/logger', () => ({
  info: jest.fn(),
  error: jest.fn(),
  http: jest.fn(),
  log: jest.fn(),
  warn: jest.fn(),
}));

describe('API Routes', () => {
  let app: Express;
  let mockDiscovery: jest.Mocked<ServiceDiscovery>;
  let mockAggregator: jest.Mocked<SpecAggregator>;

  const mockServices: ServiceConfig[] = [
    {
      name: 'service1',
      url: 'http://localhost:5000',
      healthEndpoint: '/health',
      specEndpoint: '/openapi.json',
      description: 'Test service 1',
    },
    {
      name: 'service2',
      url: 'http://localhost:5001',
      healthEndpoint: '/health',
      specEndpoint: '/openapi.json',
      description: 'Test service 2',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    mockDiscovery = new ServiceDiscovery(mockServices) as jest.Mocked<ServiceDiscovery>;
    mockAggregator = new SpecAggregator() as jest.Mocked<SpecAggregator>;

    app = express();
    app.use(express.json());
    app.use('/api', createApiRoutes(mockDiscovery, mockAggregator));
  });

  describe('GET /api/services', () => {
    it('should return list of all services', async () => {
      const mockStatuses: ServiceStatus[] = [
        {
          config: mockServices[0],
          health: { name: 'service1', status: 'healthy', responseTime: 50, lastChecked: new Date() },
          specAvailable: true,
        },
      ];

      mockDiscovery.getAllServiceStatuses.mockReturnValue(mockStatuses);

      const response = await request(app).get('/api/services');

      expect(response.status).toBe(200);
      expect(response.body.count).toBe(1);
      expect(response.body.timestamp).toBeDefined();
      expect(response.body.services).toHaveLength(1);
      expect(response.body.services[0].config.name).toBe('service1');
      expect(response.body.services[0].health.status).toBe('healthy');
      expect(response.body.services[0].specAvailable).toBe(true);
    });

    it('should return empty array when no services', async () => {
      mockDiscovery.getAllServiceStatuses.mockReturnValue([]);

      const response = await request(app).get('/api/services');

      expect(response.status).toBe(200);
      expect(response.body.services).toEqual([]);
      expect(response.body.count).toBe(0);
    });
  });

  describe('GET /api/services/:name', () => {
    it('should return service details for existing service', async () => {
      const mockStatus: ServiceStatus = {
        config: mockServices[0],
        health: { name: 'service1', status: 'healthy', responseTime: 50, lastChecked: new Date() },
        specAvailable: true,
      };

      mockDiscovery.getServiceStatus.mockReturnValue(mockStatus);

      const response = await request(app).get('/api/services/service1');

      expect(response.status).toBe(200);
      expect(response.body.config.name).toBe('service1');
      expect(response.body.health.status).toBe('healthy');
      expect(response.body.specAvailable).toBe(true);
    });

    it('should return 404 for non-existent service', async () => {
      mockDiscovery.getServiceStatus.mockReturnValue(undefined);

      const response = await request(app).get('/api/services/non-existent');

      expect(response.status).toBe(404);
      expect(response.body.error).toBe('Service not found: non-existent');
    });
  });

  describe('GET /api/specs', () => {
    it('should return aggregated specs from cache', async () => {
      const mockCachedSpecs = [
        { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} },
      ];
      const mockAggregatedSpec = {
        openapi: '3.0.0',
        info: { title: 'Aggregated', version: '1.0.0' },
        paths: {},
      };

      mockDiscovery.getAllCachedSpecs.mockReturnValue(mockCachedSpecs as any);
      mockAggregator.mergeSpecs.mockReturnValue(mockAggregatedSpec as any);

      const response = await request(app).get('/api/specs');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(mockAggregatedSpec);
      expect(mockAggregator.mergeSpecs).toHaveBeenCalledWith(mockCachedSpecs);
    });

    it('should fetch specs when cache is empty', async () => {
      const mockFetchedSpecs = [
        { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} },
      ];
      const mockAggregatedSpec = {
        openapi: '3.0.0',
        info: { title: 'Aggregated', version: '1.0.0' },
        paths: {},
      };

      mockDiscovery.getAllCachedSpecs.mockReturnValue([]);
      mockDiscovery.fetchAllServiceSpecs.mockResolvedValue(mockFetchedSpecs as any);
      mockAggregator.mergeSpecs.mockReturnValue(mockAggregatedSpec as any);

      const response = await request(app).get('/api/specs');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(mockAggregatedSpec);
      expect(mockDiscovery.fetchAllServiceSpecs).toHaveBeenCalled();
    });

    it('should return 500 when aggregation fails', async () => {
      mockDiscovery.getAllCachedSpecs.mockReturnValue([]);
      mockDiscovery.fetchAllServiceSpecs.mockRejectedValue(new Error('Fetch failed'));

      const response = await request(app).get('/api/specs');

      expect(response.status).toBe(500);
      expect(response.body.error).toBe('Failed to aggregate specifications');
      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe('GET /api/specs/:service', () => {
    it('should return cached spec for service', async () => {
      const mockSpec = { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} };

      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.getCachedSpec.mockReturnValue(mockSpec as any);

      const response = await request(app).get('/api/specs/service1');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(mockSpec);
    });

    it('should fetch spec when not cached', async () => {
      const mockSpec = { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} };

      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.getCachedSpec.mockReturnValue(undefined);
      mockDiscovery.fetchServiceSpec.mockResolvedValue(mockSpec as any);

      const response = await request(app).get('/api/specs/service1');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(mockSpec);
      expect(mockDiscovery.fetchServiceSpec).toHaveBeenCalledWith(mockServices[0]);
    });

    it('should return 404 for non-existent service', async () => {
      mockDiscovery.getService.mockReturnValue(undefined);

      const response = await request(app).get('/api/specs/non-existent');

      expect(response.status).toBe(404);
      expect(response.body.error).toBe('Service not found: non-existent');
    });

    it('should return 503 when spec cannot be fetched', async () => {
      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.getCachedSpec.mockReturnValue(undefined);
      mockDiscovery.fetchServiceSpec.mockResolvedValue(null);

      const response = await request(app).get('/api/specs/service1');

      expect(response.status).toBe(503);
      expect(response.body.error).toContain('Failed to fetch specification');
    });

    it('should return 500 when fetch throws error', async () => {
      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.getCachedSpec.mockReturnValue(undefined);
      mockDiscovery.fetchServiceSpec.mockRejectedValue(new Error('Network error'));

      const response = await request(app).get('/api/specs/service1');

      expect(response.status).toBe(500);
      expect(response.body.error).toBe('Failed to fetch service specification');
      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe('POST /api/refresh', () => {
    it('should refresh all services', async () => {
      const mockSpecs = [
        { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} },
      ];
      const mockHealth: ServiceHealth[] = [
        { name: 'service1', status: 'healthy', responseTime: 50, lastChecked: new Date() },
      ];

      mockDiscovery.getServices.mockReturnValue(mockServices);
      mockDiscovery.fetchAllServiceSpecs.mockResolvedValue(mockSpecs as any);
      mockDiscovery.checkAllServicesHealth.mockResolvedValue(mockHealth);

      const response = await request(app).post('/api/refresh');

      expect(response.status).toBe(200);
      expect(response.body.message).toBe('Refresh completed');
      expect(response.body.services.total).toBe(2);
      expect(response.body.services.specsFound).toBe(1);
      expect(response.body.services.healthyServices).toBe(1);
      expect(mockDiscovery.clearCaches).toHaveBeenCalled();
    });

    it('should return 500 when refresh fails', async () => {
      mockDiscovery.clearCaches.mockImplementation(() => {});
      mockDiscovery.fetchAllServiceSpecs.mockRejectedValue(new Error('Refresh failed'));

      const response = await request(app).post('/api/refresh');

      expect(response.status).toBe(500);
      expect(response.body.error).toBe('Failed to refresh services');
      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe('POST /api/refresh/:service', () => {
    it('should refresh specific service', async () => {
      const mockSpec = { openapi: '3.0.0', info: { title: 'Service 1', version: '1.0.0' }, paths: {} };
      const mockHealth: ServiceHealth = {
        name: 'service1',
        status: 'healthy',
        responseTime: 50,
        lastChecked: new Date(),
      };

      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.fetchServiceSpec.mockResolvedValue(mockSpec as any);
      mockDiscovery.checkServiceHealth.mockResolvedValue(mockHealth);

      const response = await request(app).post('/api/refresh/service1');

      expect(response.status).toBe(200);
      expect(response.body.message).toBe('Refresh completed for service1');
      expect(response.body.service.name).toBe('service1');
      expect(response.body.service.specAvailable).toBe(true);
      expect(response.body.service.health).toBe('healthy');
      expect(mockDiscovery.clearServiceCache).toHaveBeenCalledWith('service1');
    });

    it('should return 404 for non-existent service', async () => {
      mockDiscovery.getService.mockReturnValue(undefined);

      const response = await request(app).post('/api/refresh/non-existent');

      expect(response.status).toBe(404);
      expect(response.body.error).toBe('Service not found: non-existent');
    });

    it('should return 500 when refresh fails', async () => {
      mockDiscovery.getService.mockReturnValue(mockServices[0]);
      mockDiscovery.clearServiceCache.mockImplementation(() => {});
      mockDiscovery.fetchServiceSpec.mockRejectedValue(new Error('Network error'));

      const response = await request(app).post('/api/refresh/service1');

      expect(response.status).toBe(500);
      expect(response.body.error).toBe('Failed to refresh service');
      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe('GET /api/status', () => {
    it('should return comprehensive system status', async () => {
      const mockStatuses: ServiceStatus[] = [
        {
          config: mockServices[0],
          health: { name: 'service1', status: 'healthy', responseTime: 50, lastChecked: new Date() },
          specAvailable: true,
        },
        {
          config: mockServices[1],
          health: { name: 'service2', status: 'unhealthy', responseTime: 0, lastChecked: new Date() },
          specAvailable: false,
        },
      ];

      mockDiscovery.getAllServiceStatuses.mockReturnValue(mockStatuses);

      const response = await request(app).get('/api/status');

      expect(response.status).toBe(200);
      expect(response.body.aggregator).toBeDefined();
      expect(response.body.aggregator.name).toBe('Swagger Aggregator Service');
      expect(response.body.services.total).toBe(2);
      expect(response.body.services.healthy).toBe(1);
      expect(response.body.services.unhealthy).toBe(1);
      expect(response.body.services.specsAvailable).toBe(1);
      expect(response.body.details).toHaveLength(2);
    });

    it('should handle empty services list', async () => {
      mockDiscovery.getAllServiceStatuses.mockReturnValue([]);

      const response = await request(app).get('/api/status');

      expect(response.status).toBe(200);
      expect(response.body.services.total).toBe(0);
      expect(response.body.services.healthy).toBe(0);
    });
  });
});

