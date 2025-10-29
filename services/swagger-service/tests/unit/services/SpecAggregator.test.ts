/**
 * Unit tests for SpecAggregator
 */
import { SpecAggregator } from '../../../src/services/SpecAggregator';
import { ServiceConfig } from '../../../src/types/service.types';
import { OpenAPISpec } from '../../../src/types/openapi.types';

describe('SpecAggregator', () => {
  let specAggregator: SpecAggregator;

  const mockService1: ServiceConfig = {
    name: 'User Service',
    url: 'http://localhost:5000',
    healthEndpoint: '/health',
    specEndpoint: '/openapi.json',
    description: 'User management service',
  };

  const mockService2: ServiceConfig = {
    name: 'Order Service',
    url: 'http://localhost:5001',
    healthEndpoint: '/health',
    specEndpoint: '/openapi.json',
    description: 'Order management service',
  };

  const mockSpec1: OpenAPISpec = {
    openapi: '3.0.0',
    info: {
      title: 'User API',
      version: '1.0.0',
    },
    paths: {
      '/users': {
        get: {
          summary: 'Get users',
          responses: {
            '200': {
              description: 'Success',
            },
          },
        },
      },
    },
    components: {
      schemas: {
        User: {
          type: 'object',
          properties: {
            id: { type: 'integer' },
            name: { type: 'string' },
          },
        },
      },
    },
    tags: [
      {
        name: 'Users',
        description: 'User operations',
      },
    ],
  };

  const mockSpec2: OpenAPISpec = {
    openapi: '3.0.0',
    info: {
      title: 'Order API',
      version: '1.0.0',
    },
    paths: {
      '/orders': {
        post: {
          summary: 'Create order',
          responses: {
            '201': {
              description: 'Created',
            },
          },
        },
      },
    },
  };

  beforeEach(() => {
    specAggregator = new SpecAggregator();
  });

  describe('mergeSpecs', () => {
    it('should return empty spec when no services provided', () => {
      const aggregated = specAggregator.mergeSpecs([]);

      expect(aggregated.openapi).toBe('3.0.0');
      expect(aggregated.paths).toEqual({});
      expect(aggregated['x-services']).toEqual([]);
    });

    it('should merge single service spec', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
      ]);

      expect(aggregated.openapi).toBe('3.0.0');
      expect(aggregated.paths).toHaveProperty('/user-service/users');
      expect(aggregated['x-services']).toHaveLength(1);
    });

    it('should merge multiple service specs', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
        { service: mockService2, spec: mockSpec2 },
      ]);

      expect(aggregated.paths).toHaveProperty('/user-service/users');
      expect(aggregated.paths).toHaveProperty('/order-service/orders');
      expect(aggregated['x-services']).toHaveLength(2);
    });

    it('should prefix paths with service name', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
      ]);

      expect(Object.keys(aggregated.paths)[0]).toBe('/user-service/users');
    });

    it('should add service tags to operations', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
      ]);

      const path = aggregated.paths['/user-service/users'];
      expect(path).toBeDefined();
      expect(path?.get?.tags).toContain('User Service');
    });

    it('should prefix component schemas with service name', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
      ]);

      expect(aggregated.components?.schemas).toHaveProperty('user-service_User');
    });

    it('should merge tags from multiple services', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
        { service: mockService2, spec: mockSpec2 },
      ]);

      expect(aggregated.tags).toBeDefined();
      expect(aggregated.tags?.length).toBeGreaterThan(0);
    });

    it('should add service-specific tags', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
      ]);

      const serviceTag = aggregated.tags?.find(
        (tag) => tag.name === 'User Service'
      );
      expect(serviceTag).toBeDefined();
      expect(serviceTag?.description).toBe(mockService1.description);
    });

    it('should handle specs without components', () => {
      const specWithoutComponents: OpenAPISpec = {
        openapi: '3.0.0',
        info: { title: 'Simple API', version: '1.0.0' },
        paths: {
          '/test': {
            get: {
              responses: { '200': { description: 'OK' } },
            },
          },
        },
      };

      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: specWithoutComponents },
      ]);

      expect(aggregated.paths).toHaveProperty('/user-service/test');
    });

    it('should handle specs without tags', () => {
      const specWithoutTags: OpenAPISpec = {
        openapi: '3.0.0',
        info: { title: 'Simple API', version: '1.0.0' },
        paths: {},
      };

      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: specWithoutTags },
      ]);

      expect(aggregated.tags).toBeDefined();
    });

    it('should merge servers from multiple services', () => {
      const specWithServers: OpenAPISpec = {
        openapi: '3.0.0',
        info: { title: 'API', version: '1.0.0' },
        paths: {},
        servers: [
          {
            url: 'http://localhost:5000',
            description: 'Development server',
          },
        ],
      };

      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: specWithServers },
      ]);

      expect(aggregated.servers?.length).toBeGreaterThan(0);
      const serviceServer = aggregated.servers?.find((s) =>
        s.description?.includes('User Service')
      );
      expect(serviceServer).toBeDefined();
    });

    it('should create proper x-services metadata', () => {
      const aggregated = specAggregator.mergeSpecs([
        { service: mockService1, spec: mockSpec1 },
        { service: mockService2, spec: mockSpec2 },
      ]);

      expect(aggregated['x-services']).toHaveLength(2);
      expect(aggregated['x-services'][0]).toHaveProperty('name');
      expect(aggregated['x-services'][0]).toHaveProperty('version');
      expect(aggregated['x-services'][0]).toHaveProperty('pathPrefix');
    });

    it('should sanitize service names in paths', () => {
      const serviceWithSpecialChars: ServiceConfig = {
        ...mockService1,
        name: 'User & Profile Service',
      };

      const aggregated = specAggregator.mergeSpecs([
        { service: serviceWithSpecialChars, spec: mockSpec1 },
      ]);

      const firstPath = Object.keys(aggregated.paths)[0];
      expect(firstPath).toMatch(/^\/[a-z0-9-]+\//);
    });
  });

  describe('getSingleServiceSpec', () => {
    it('should return spec with modified title', () => {
      const result = specAggregator.getSingleServiceSpec(
        mockService1,
        mockSpec1
      );

      expect(result.info.title).toContain('User Service');
      expect(result.info.title).toContain('User API');
    });

    it('should preserve original spec data', () => {
      const result = specAggregator.getSingleServiceSpec(
        mockService1,
        mockSpec1
      );

      expect(result.paths).toEqual(mockSpec1.paths);
      expect(result.openapi).toBe(mockSpec1.openapi);
    });
  });
});

