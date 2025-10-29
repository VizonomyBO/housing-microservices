/**
 * Unit tests for ServiceDiscovery
 */
import axios from 'axios';
import { ServiceDiscovery } from '../../../src/services/ServiceDiscovery';
import { ServiceConfig } from '../../../src/types/service.types';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('ServiceDiscovery', () => {
  let serviceDiscovery: ServiceDiscovery;
  const mockServices: ServiceConfig[] = [
    {
      name: 'test-service',
      url: 'http://localhost:5000',
      healthEndpoint: '/health',
      specEndpoint: '/openapi.json',
      description: 'Test service',
      enabled: true,
    },
    {
      name: 'another-service',
      url: 'http://localhost:5001',
      healthEndpoint: '/health',
      specEndpoint: '/api/spec',
      description: 'Another service',
      enabled: true,
    },
    {
      name: 'disabled-service',
      url: 'http://localhost:5002',
      healthEndpoint: '/health',
      specEndpoint: '/spec',
      description: 'Disabled service',
      enabled: false,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    serviceDiscovery = new ServiceDiscovery(mockServices);
  });

  describe('constructor', () => {
    it('should filter out disabled services', () => {
      const services = serviceDiscovery.getServices();
      expect(services).toHaveLength(2);
      expect(services.find((s) => s.name === 'disabled-service')).toBeUndefined();
    });

    it('should include all enabled services', () => {
      const services = serviceDiscovery.getServices();
      expect(services.find((s) => s.name === 'test-service')).toBeDefined();
      expect(services.find((s) => s.name === 'another-service')).toBeDefined();
    });
  });

  describe('getServices', () => {
    it('should return all registered services', () => {
      const services = serviceDiscovery.getServices();
      expect(services).toEqual(
        mockServices.filter((s) => s.enabled !== false)
      );
    });
  });

  describe('getService', () => {
    it('should return service by name', () => {
      const service = serviceDiscovery.getService('test-service');
      expect(service).toBeDefined();
      expect(service?.name).toBe('test-service');
    });

    it('should return undefined for non-existent service', () => {
      const service = serviceDiscovery.getService('non-existent');
      expect(service).toBeUndefined();
    });
  });

  describe('checkServiceHealth', () => {
    it('should mark service as healthy on successful health check', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { status: 'ok' },
      });

      const health = await serviceDiscovery.checkServiceHealth(mockServices[0]);

      expect(health.status).toBe('healthy');
      expect(health.name).toBe('test-service');
      expect(health.responseTime).toBeGreaterThanOrEqual(0);
      expect(health.lastChecked).toBeInstanceOf(Date);
      expect(mockedAxios.get).toHaveBeenCalledWith(
        'http://localhost:5000/health',
        expect.objectContaining({
          timeout: expect.any(Number),
        })
      );
    });

    it('should mark service as unhealthy on non-200 response', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 503,
        data: { error: 'Service unavailable' },
      });

      const health = await serviceDiscovery.checkServiceHealth(mockServices[0]);

      expect(health.status).toBe('unhealthy');
      expect(health.name).toBe('test-service');
    });

    it('should mark service as unhealthy on network error', async () => {
      mockedAxios.get.mockRejectedValue(new Error('Network error'));

      const health = await serviceDiscovery.checkServiceHealth(mockServices[0]);

      expect(health.status).toBe('unhealthy');
      expect(health.error).toBeDefined();
    });

    it('should cache health status', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { status: 'ok' },
      });

      await serviceDiscovery.checkServiceHealth(mockServices[0]);
      const cached = serviceDiscovery.getCachedHealth('test-service');

      expect(cached).toBeDefined();
      expect(cached?.status).toBe('healthy');
    });
  });

  describe('checkAllServicesHealth', () => {
    it('should check health of all services', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { status: 'ok' },
      });

      const healthResults = await serviceDiscovery.checkAllServicesHealth();

      expect(healthResults).toHaveLength(2);
      expect(mockedAxios.get).toHaveBeenCalledTimes(2);
    });
  });

  describe('getCachedHealth', () => {
    it('should return cached health status', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { status: 'ok' },
      });

      await serviceDiscovery.checkServiceHealth(mockServices[0]);
      const cached = serviceDiscovery.getCachedHealth('test-service');

      expect(cached).toBeDefined();
      expect(cached?.name).toBe('test-service');
    });

    it('should return undefined for non-cached service', () => {
      const cached = serviceDiscovery.getCachedHealth('non-existent');
      expect(cached).toBeUndefined();
    });
  });

  describe('getAllCachedHealth', () => {
    it('should return all cached health statuses', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { status: 'ok' },
      });

      await serviceDiscovery.checkAllServicesHealth();
      const allCached = serviceDiscovery.getAllCachedHealth();

      expect(allCached).toHaveLength(2);
    });
  });

  describe('fetchServiceSpec', () => {
    it('should fetch OpenAPI spec successfully', async () => {
      const mockSpec = {
        openapi: '3.0.0',
        info: { title: 'Test API', version: '1.0.0' },
        paths: {},
      };

      mockedAxios.get.mockResolvedValue({
        data: mockSpec,
      });

      const spec = await serviceDiscovery.fetchServiceSpec(mockServices[0]);

      expect(spec).toEqual(mockSpec);
      expect(mockedAxios.get).toHaveBeenCalledWith(
        'http://localhost:5000/openapi.json',
        expect.objectContaining({
          headers: { Accept: 'application/json' },
        })
      );
    });

    it('should return null on fetch error', async () => {
      mockedAxios.get.mockRejectedValue(new Error('Fetch error'));

      const spec = await serviceDiscovery.fetchServiceSpec(mockServices[0]);

      expect(spec).toBeNull();
    });

    it('should cache fetched spec', async () => {
      const mockSpec = {
        openapi: '3.0.0',
        info: { title: 'Test API', version: '1.0.0' },
        paths: {},
      };

      mockedAxios.get.mockResolvedValue({ data: mockSpec });

      await serviceDiscovery.fetchServiceSpec(mockServices[0]);
      const cached = serviceDiscovery.getCachedSpec('test-service');

      expect(cached).toEqual(mockSpec);
    });
  });

  describe('fetchAllServiceSpecs', () => {
    it('should fetch specs from all services', async () => {
      const mockSpec = {
        openapi: '3.0.0',
        info: { title: 'Test API', version: '1.0.0' },
        paths: {},
      };

      mockedAxios.get.mockResolvedValue({ data: mockSpec });

      const specs = await serviceDiscovery.fetchAllServiceSpecs();

      expect(specs).toHaveLength(2);
      expect(specs[0].spec).toEqual(mockSpec);
    });

    it('should skip services that fail to fetch', async () => {
      mockedAxios.get
        .mockResolvedValueOnce({ data: { openapi: '3.0.0', info: {}, paths: {} } })
        .mockRejectedValueOnce(new Error('Fetch error'));

      const specs = await serviceDiscovery.fetchAllServiceSpecs();

      expect(specs).toHaveLength(1);
    });
  });

  describe('getHealthyServices', () => {
    it('should return only healthy services', async () => {
      mockedAxios.get
        .mockResolvedValueOnce({ status: 200, data: {} })
        .mockResolvedValueOnce({ status: 503, data: {} });

      await serviceDiscovery.checkAllServicesHealth();
      const healthy = serviceDiscovery.getHealthyServices();

      expect(healthy).toHaveLength(1);
      expect(healthy[0].name).toBe('test-service');
    });
  });

  describe('clearCaches', () => {
    it('should clear all caches', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { openapi: '3.0.0', info: {}, paths: {} },
      });

      await serviceDiscovery.checkServiceHealth(mockServices[0]);
      await serviceDiscovery.fetchServiceSpec(mockServices[0]);

      serviceDiscovery.clearCaches();

      expect(serviceDiscovery.getCachedHealth('test-service')).toBeUndefined();
      expect(serviceDiscovery.getCachedSpec('test-service')).toBeUndefined();
    });
  });

  describe('clearServiceCache', () => {
    it('should clear cache for specific service', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { openapi: '3.0.0', info: {}, paths: {} },
      });

      await serviceDiscovery.checkAllServicesHealth();
      serviceDiscovery.clearServiceCache('test-service');

      expect(serviceDiscovery.getCachedHealth('test-service')).toBeUndefined();
      expect(serviceDiscovery.getCachedHealth('another-service')).toBeDefined();
    });
  });

  describe('getServiceStatus', () => {
    it('should return combined service status', async () => {
      mockedAxios.get.mockResolvedValue({
        status: 200,
        data: { openapi: '3.0.0', info: {}, paths: {} },
      });

      await serviceDiscovery.checkServiceHealth(mockServices[0]);
      await serviceDiscovery.fetchServiceSpec(mockServices[0]);

      const status = serviceDiscovery.getServiceStatus('test-service');

      expect(status).toBeDefined();
      expect(status?.config.name).toBe('test-service');
      expect(status?.health.status).toBe('healthy');
      expect(status?.specAvailable).toBe(true);
    });

    it('should return undefined for non-existent service', () => {
      const status = serviceDiscovery.getServiceStatus('non-existent');
      expect(status).toBeUndefined();
    });
  });

  describe('getAllServiceStatuses', () => {
    it('should return statuses for all services', async () => {
      mockedAxios.get.mockResolvedValue({ status: 200, data: {} });

      await serviceDiscovery.checkAllServicesHealth();
      const statuses = serviceDiscovery.getAllServiceStatuses();

      expect(statuses).toHaveLength(2);
      expect(statuses[0].config.name).toBe('test-service');
    });
  });
});

