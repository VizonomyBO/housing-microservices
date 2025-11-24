/**
 * Unit tests for health routes
 */
import request from 'supertest';
import express, { Express } from 'express';
import { createHealthRoutes } from '../../../src/routes/health.routes';
import { HealthMonitor } from '../../../src/services/HealthMonitor';
import { ServiceDiscovery } from '../../../src/services/ServiceDiscovery';
import { ServiceConfig } from '../../../src/types/service.types';

jest.mock('../../../src/services/HealthMonitor');
jest.mock('../../../src/services/ServiceDiscovery');

describe('Health Routes', () => {
  let app: Express;
  let mockHealthMonitor: jest.Mocked<HealthMonitor>;
  let mockDiscovery: jest.Mocked<ServiceDiscovery>;

  const mockServices: ServiceConfig[] = [
    {
      name: 'service1',
      url: 'http://localhost:5000',
      healthEndpoint: '/health',
      specEndpoint: '/spec',
      description: 'Test service 1',
    },
  ];

  beforeEach(() => {
    mockDiscovery = new ServiceDiscovery(mockServices) as jest.Mocked<ServiceDiscovery>;
    mockHealthMonitor = new HealthMonitor(mockDiscovery) as jest.Mocked<HealthMonitor>;

    app = express();
    app.use(express.json());
    app.use('/', createHealthRoutes(mockHealthMonitor));
  });

  describe('GET /health', () => {
    it('should return health status when healthy', async () => {
      mockHealthMonitor.getCurrentHealth.mockResolvedValue({
        status: 'healthy',
        timestamp: new Date(),
        services: {},
        aggregator: {
          uptime: 100,
          version: '1.0.0',
          memory: { used: 50, total: 100, percentage: 50 },
        },
      });

      const response = await request(app).get('/health');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('healthy');
      expect(response.body.aggregator).toBeDefined();
    });

    it('should return 503 when unhealthy', async () => {
      mockHealthMonitor.getCurrentHealth.mockResolvedValue({
        status: 'unhealthy',
        timestamp: new Date(),
        services: {},
        aggregator: {
          uptime: 100,
          version: '1.0.0',
          memory: { used: 50, total: 100, percentage: 50 },
        },
      });

      const response = await request(app).get('/health');

      expect(response.status).toBe(503);
      expect(response.body.status).toBe('unhealthy');
    });

    it('should return 500 when health check fails', async () => {
      mockHealthMonitor.getCurrentHealth.mockRejectedValue(new Error('Health check failed'));

      const response = await request(app).get('/health');

      expect(response.status).toBe(500);
      expect(response.body.status).toBe('unhealthy');
      expect(response.body.error).toBe('Failed to check health');
    });

    it('should include timestamp in response', async () => {
      const mockDate = new Date('2024-01-01T00:00:00Z');
      mockHealthMonitor.getCurrentHealth.mockResolvedValue({
        status: 'healthy',
        timestamp: mockDate,
        services: {},
        aggregator: {
          uptime: 100,
          version: '1.0.0',
          memory: { used: 50, total: 100, percentage: 50 },
        },
      });

      const response = await request(app).get('/health');

      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe('GET /health/metrics', () => {
    it('should return all metrics', async () => {
      const mockMetrics = [
        {
          serviceName: 'service1',
          checks: 10,
          successRate: 100,
          averageResponseTime: 50,
        },
      ];

      mockHealthMonitor.getAllMetrics.mockReturnValue(mockMetrics as any);

      const response = await request(app).get('/health/metrics');

      expect(response.status).toBe(200);
      expect(response.body.metrics).toEqual(mockMetrics);
      expect(response.body.timestamp).toBeDefined();
    });

    it('should return empty metrics array when no metrics available', async () => {
      mockHealthMonitor.getAllMetrics.mockReturnValue([]);

      const response = await request(app).get('/health/metrics');

      expect(response.status).toBe(200);
      expect(response.body.metrics).toEqual([]);
    });
  });

  describe('GET /health/metrics/:service', () => {
    it('should return metrics for a specific service', async () => {
      const mockMetrics = {
        serviceName: 'service1',
        checks: 10,
        successRate: 100,
        averageResponseTime: 50,
      };

      mockHealthMonitor.getServiceMetrics.mockReturnValue(mockMetrics as any);

      const response = await request(app).get('/health/metrics/service1');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(mockMetrics);
    });

    it('should return 404 when service metrics not found', async () => {
      mockHealthMonitor.getServiceMetrics.mockReturnValue(undefined);

      const response = await request(app).get('/health/metrics/non-existent');

      expect(response.status).toBe(404);
      expect(response.body.error).toBe('No metrics found for service: non-existent');
    });

    it('should handle service names with special characters', async () => {
      mockHealthMonitor.getServiceMetrics.mockReturnValue(undefined);

      const response = await request(app).get('/health/metrics/service-name');

      expect(response.status).toBe(404);
      expect(response.body.error).toContain('service-name');
    });
  });
});

