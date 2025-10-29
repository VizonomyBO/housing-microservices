/**
 * Service discovery and health monitoring
 */
import axios, { AxiosError } from 'axios';
import { ServiceConfig, ServiceHealth, ServiceStatus } from '../types/service.types';
import { OpenAPISpec } from '../types/openapi.types';
import logger from '../utils/logger';
import config from '../config/environment';

export class ServiceDiscovery {
  private services: ServiceConfig[];
  private healthCache: Map<string, ServiceHealth>;
  private specCache: Map<string, OpenAPISpec>;

  constructor(services: ServiceConfig[]) {
    this.services = services.filter((s) => s.enabled !== false);
    this.healthCache = new Map();
    this.specCache = new Map();
  }

  /**
   * Get all registered services
   */
  getServices(): ServiceConfig[] {
    return this.services;
  }

  /**
   * Get a service by name
   */
  getService(name: string): ServiceConfig | undefined {
    return this.services.find((s) => s.name === name);
  }

  /**
   * Check health of a single service
   */
  async checkServiceHealth(service: ServiceConfig): Promise<ServiceHealth> {
    const startTime = Date.now();

    try {
      const response = await axios.get(`${service.url}${service.healthEndpoint}`, {
        timeout: config.httpTimeout,
        validateStatus: (status) => status < 500,
      });

      const responseTime = Date.now() - startTime;

      const health: ServiceHealth = {
        name: service.name,
        status: response.status === 200 ? 'healthy' : 'unhealthy',
        responseTime,
        lastChecked: new Date(),
        metadata: response.data,
      };

      this.healthCache.set(service.name, health);
      return health;
    } catch (error) {
      const responseTime = Date.now() - startTime;
      const errorMessage = error instanceof AxiosError ? error.message : 'Unknown error';

      const health: ServiceHealth = {
        name: service.name,
        status: 'unhealthy',
        responseTime,
        lastChecked: new Date(),
        error: errorMessage,
      };

      this.healthCache.set(service.name, health);
      logger.error(`Health check failed for ${service.name}: ${errorMessage}`);
      return health;
    }
  }

  /**
   * Check health of all services
   */
  async checkAllServicesHealth(): Promise<ServiceHealth[]> {
    const healthChecks = this.services.map((service) => this.checkServiceHealth(service));

    return Promise.all(healthChecks);
  }

  /**
   * Get cached health status for a service
   */
  getCachedHealth(serviceName: string): ServiceHealth | undefined {
    return this.healthCache.get(serviceName);
  }

  /**
   * Get all cached health statuses
   */
  getAllCachedHealth(): ServiceHealth[] {
    return Array.from(this.healthCache.values());
  }

  /**
   * Fetch OpenAPI spec from a service
   */
  async fetchServiceSpec(service: ServiceConfig): Promise<OpenAPISpec | null> {
    try {
      const response = await axios.get<OpenAPISpec>(`${service.url}${service.specEndpoint}`, {
        timeout: config.httpTimeout,
        headers: {
          Accept: 'application/json',
        },
      });

      this.specCache.set(service.name, response.data);
      logger.info(`Fetched OpenAPI spec for ${service.name}`);
      return response.data;
    } catch (error) {
      const errorMessage = error instanceof AxiosError ? error.message : 'Unknown error';

      logger.error(`Failed to fetch spec for ${service.name}: ${errorMessage}`);
      return null;
    }
  }

  /**
   * Fetch specs from all healthy services
   */
  async fetchAllServiceSpecs(): Promise<Array<{ service: ServiceConfig; spec: OpenAPISpec }>> {
    const specs: Array<{ service: ServiceConfig; spec: OpenAPISpec }> = [];

    for (const service of this.services) {
      const spec = await this.fetchServiceSpec(service);
      if (spec) {
        specs.push({ service, spec });
      }
    }

    return specs;
  }

  /**
   * Get cached spec for a service
   */
  getCachedSpec(serviceName: string): OpenAPISpec | undefined {
    return this.specCache.get(serviceName);
  }

  /**
   * Get all cached specs
   */
  getAllCachedSpecs(): Array<{ service: ServiceConfig; spec: OpenAPISpec }> {
    const specs: Array<{ service: ServiceConfig; spec: OpenAPISpec }> = [];

    for (const service of this.services) {
      const spec = this.specCache.get(service.name);
      if (spec) {
        specs.push({ service, spec });
      }
    }

    return specs;
  }

  /**
   * Get healthy services
   */
  getHealthyServices(): ServiceConfig[] {
    return this.services.filter((service) => {
      const health = this.healthCache.get(service.name);
      return health?.status === 'healthy';
    });
  }

  /**
   * Get service status (combined health and spec availability)
   */
  getServiceStatus(serviceName: string): ServiceStatus | undefined {
    const service = this.getService(serviceName);
    if (!service) {
      return undefined;
    }

    const health = this.getCachedHealth(serviceName) || {
      name: serviceName,
      status: 'unknown' as const,
      lastChecked: new Date(),
    };

    const specAvailable = this.specCache.has(serviceName);

    return {
      config: service,
      health,
      specAvailable,
    };
  }

  /**
   * Get all service statuses
   */
  getAllServiceStatuses(): ServiceStatus[] {
    return this.services.map((service) => ({
      config: service,
      health: this.getCachedHealth(service.name) || {
        name: service.name,
        status: 'unknown' as const,
        lastChecked: new Date(),
      },
      specAvailable: this.specCache.has(service.name),
    }));
  }

  /**
   * Clear all caches
   */
  clearCaches(): void {
    this.healthCache.clear();
    this.specCache.clear();
    logger.info('Cleared all service caches');
  }

  /**
   * Clear cache for a specific service
   */
  clearServiceCache(serviceName: string): void {
    this.healthCache.delete(serviceName);
    this.specCache.delete(serviceName);
    logger.info(`Cleared cache for ${serviceName}`);
  }
}
