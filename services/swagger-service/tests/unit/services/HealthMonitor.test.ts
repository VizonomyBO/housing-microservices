/**
 * Unit tests for HealthMonitor
 */
import { HealthMonitor } from '../../../src/services/HealthMonitor';
import { ServiceDiscovery } from '../../../src/services/ServiceDiscovery';
import { ServiceConfig, ServiceHealth } from '../../../src/types/service.types';

jest.mock('../../../src/services/ServiceDiscovery');

describe('HealthMonitor', () => {
  let healthMonitor: HealthMonitor;
  let mockDiscovery: jest.Mocked<ServiceDiscovery>;

  const mockServices: ServiceConfig[] = [
    {
      name: 'service1',
      url: 'http://localhost:5000',
      healthEndpoint: '/health',
      specEndpoint: '/spec',
      description: 'Test service 1',
    },
    {
      name: 'service2',
      url: 'http://localhost:5001',
      healthEndpoint: '/health',
      specEndpoint: '/spec',
      description: 'Test service 2',
    },
  ];

  beforeEach(() => {
    mockDiscovery = new ServiceDiscovery(
      mockServices
    ) as jest.Mocked<ServiceDiscovery>;
    healthMonitor = new HealthMonitor(mockDiscovery);

    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    healthMonitor.stop();
  });

  describe('start', () => {
    it('should start periodic health monitoring', () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([]);

      healthMonitor.start();

      expect(mockDiscovery.checkAllServicesHealth).toHaveBeenCalledTimes(1);
    });

    it('should not start if already running', () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([]);

      healthMonitor.start();
      healthMonitor.start(); // Try to start again

      // Should only be called once from first start
      expect(mockDiscovery.checkAllServicesHealth).toHaveBeenCalledTimes(1);
    });

    it('should schedule periodic checks', async () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([]);

      healthMonitor.start();

      // Fast forward time
      jest.advanceTimersByTime(60000); // 1 minute
      await Promise.resolve();

      expect(mockDiscovery.checkAllServicesHealth).toHaveBeenCalledTimes(2);
    });
  });

  describe('stop', () => {
    it('should stop health monitoring', () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([]);

      healthMonitor.start();
      healthMonitor.stop();

      // Fast forward time after stopping
      const callCountBeforeStop = mockDiscovery.checkAllServicesHealth.mock.calls.length;
      jest.advanceTimersByTime(60000);

      expect(mockDiscovery.checkAllServicesHealth).toHaveBeenCalledTimes(
        callCountBeforeStop
      );
    });

    it('should be idempotent', () => {
      healthMonitor.stop();
      healthMonitor.stop(); // Should not throw

      expect(true).toBe(true);
    });
  });

  describe('getCurrentHealth', () => {
    it('should return healthy status when all services are healthy', async () => {
      const mockHealthyStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
        {
          name: 'service2',
          status: 'healthy',
          responseTime: 60,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.getAllCachedHealth.mockReturnValue(mockHealthyStatus);

      const result = await healthMonitor.getCurrentHealth();

      expect(result.status).toBe('healthy');
      expect(result.services['service1'].status).toBe('up');
      expect(result.services['service2'].status).toBe('up');
    });

    it('should return degraded status when some services are unhealthy', async () => {
      const mockMixedStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
        {
          name: 'service2',
          status: 'unhealthy',
          responseTime: 0,
          lastChecked: new Date(),
          error: 'Connection failed',
        },
      ];

      mockDiscovery.getAllCachedHealth.mockReturnValue(mockMixedStatus);

      const result = await healthMonitor.getCurrentHealth();

      expect(result.status).toBe('degraded');
      expect(result.services['service1'].status).toBe('up');
      expect(result.services['service2'].status).toBe('down');
      expect(result.services['service2'].error).toBe('Connection failed');
    });

    it('should return unhealthy status when all services are unhealthy', async () => {
      const mockUnhealthyStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'unhealthy',
          responseTime: 0,
          lastChecked: new Date(),
        },
        {
          name: 'service2',
          status: 'unhealthy',
          responseTime: 0,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.getAllCachedHealth.mockReturnValue(mockUnhealthyStatus);

      const result = await healthMonitor.getCurrentHealth();

      expect(result.status).toBe('unhealthy');
    });

    it('should include aggregator metadata', async () => {
      mockDiscovery.getAllCachedHealth.mockReturnValue([]);

      const result = await healthMonitor.getCurrentHealth();

      expect(result.aggregator).toBeDefined();
      expect(result.aggregator.uptime).toBeDefined();
      expect(result.aggregator.version).toBeDefined();
      expect(result.aggregator.memory).toBeDefined();
    });

    it('should include timestamp', async () => {
      mockDiscovery.getAllCachedHealth.mockReturnValue([]);

      const result = await healthMonitor.getCurrentHealth();

      expect(result.timestamp).toBeInstanceOf(Date);
    });
  });

  describe('metrics tracking', () => {
    it('should track successful checks', async () => {
      const mockHealthyStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.checkAllServicesHealth.mockResolvedValue(mockHealthyStatus);

      healthMonitor.start();
      await Promise.resolve();

      const metrics = healthMonitor.getServiceMetrics('service1');

      expect(metrics).toBeDefined();
      expect(metrics?.checks).toBeGreaterThan(0);
      expect(metrics?.successRate).toBe(100);
    });

    it('should track failed checks', async () => {
      const mockUnhealthyStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'unhealthy',
          responseTime: 0,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.checkAllServicesHealth.mockResolvedValue(
        mockUnhealthyStatus
      );

      healthMonitor.start();
      await Promise.resolve();

      const metrics = healthMonitor.getServiceMetrics('service1');

      expect(metrics).toBeDefined();
      expect(metrics?.successRate).toBe(0);
      expect(metrics?.lastFailure).toBeDefined();
    });

    it('should calculate average response time', async () => {
      const mockHealthStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 100,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.checkAllServicesHealth
        .mockResolvedValueOnce([{ ...mockHealthStatus[0], responseTime: 100 }])
        .mockResolvedValueOnce([{ ...mockHealthStatus[0], responseTime: 200 }]);

      healthMonitor.start();
      await Promise.resolve();

      jest.advanceTimersByTime(60000);
      await Promise.resolve();

      const metrics = healthMonitor.getServiceMetrics('service1');

      expect(metrics?.averageResponseTime).toBeGreaterThan(0);
    });
  });

  describe('getServiceMetrics', () => {
    it('should return metrics for a service', async () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
      ]);

      healthMonitor.start();
      await Promise.resolve();

      const metrics = healthMonitor.getServiceMetrics('service1');

      expect(metrics).toBeDefined();
      expect(metrics?.serviceName).toBe('service1');
    });

    it('should return undefined for non-tracked service', () => {
      const metrics = healthMonitor.getServiceMetrics('non-existent');
      expect(metrics).toBeUndefined();
    });
  });

  describe('getAllMetrics', () => {
    it('should return all service metrics', async () => {
      const mockHealthStatus: ServiceHealth[] = [
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
        {
          name: 'service2',
          status: 'healthy',
          responseTime: 60,
          lastChecked: new Date(),
        },
      ];

      mockDiscovery.checkAllServicesHealth.mockResolvedValue(mockHealthStatus);

      healthMonitor.start();
      await Promise.resolve();

      const allMetrics = healthMonitor.getAllMetrics();

      expect(allMetrics).toHaveLength(2);
    });
  });

  describe('resetServiceMetrics', () => {
    it('should reset metrics for a specific service', async () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
      ]);

      healthMonitor.start();
      await Promise.resolve();

      healthMonitor.resetServiceMetrics('service1');

      const metrics = healthMonitor.getServiceMetrics('service1');
      expect(metrics).toBeUndefined();
    });
  });

  describe('resetAllMetrics', () => {
    it('should reset all metrics', async () => {
      mockDiscovery.checkAllServicesHealth.mockResolvedValue([
        {
          name: 'service1',
          status: 'healthy',
          responseTime: 50,
          lastChecked: new Date(),
        },
      ]);

      healthMonitor.start();
      await Promise.resolve();

      healthMonitor.resetAllMetrics();

      const allMetrics = healthMonitor.getAllMetrics();
      expect(allMetrics).toHaveLength(0);
    });
  });
});

