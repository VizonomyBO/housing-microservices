/**
 * OpenAPI specification aggregator
 */
import { OpenAPISpec, AggregatedSpec, PathItem } from '../types/openapi.types';
import { ServiceConfig } from '../types/service.types';
import logger from '../utils/logger';
import config from '../config/environment';

export class SpecAggregator {
  /**
   * Merge multiple OpenAPI specs into a single aggregated spec
   */
  mergeSpecs(serviceSpecs: Array<{ service: ServiceConfig; spec: OpenAPISpec }>): AggregatedSpec {
    if (serviceSpecs.length === 0) {
      return this.getEmptySpec();
    }

    // Start with a base spec
    const aggregated: AggregatedSpec = {
      openapi: '3.0.0',
      info: {
        title: config.appName,
        version: config.appVersion,
        description: config.appDescription,
        contact: {
          name: 'API Support',
          email: 'support@example.com',
        },
      },
      servers: [
        {
          url: `http://localhost:${config.port}`,
          description: 'Aggregator Service',
        },
      ],
      paths: {},
      components: {
        schemas: {},
        responses: {},
        parameters: {},
        securitySchemes: {},
      },
      tags: [],
      'x-services': [],
    };

    // Merge each service spec
    for (const { service, spec } of serviceSpecs) {
      this.mergeServiceSpec(aggregated, service, spec);
    }

    logger.info(`Aggregated ${serviceSpecs.length} service specifications`);
    return aggregated;
  }

  /**
   * Merge a single service spec into the aggregated spec
   */
  private mergeServiceSpec(
    aggregated: AggregatedSpec,
    service: ServiceConfig,
    spec: OpenAPISpec
  ): void {
    // Add service to x-services
    aggregated['x-services'].push({
      name: service.name,
      version: spec.info.version,
      pathPrefix: `/${this.sanitizeServiceName(service.name)}`,
    });

    const pathPrefix = `/${this.sanitizeServiceName(service.name)}`;
    const serviceExternalUrl = this.convertToExternalUrl(service.url);

    for (const [path, pathItem] of Object.entries(spec.paths)) {
      let finalPath = path;
      if (aggregated.paths[path]) {
        finalPath = `${pathPrefix}${path}`;
      }

      // Add service tag to all operations in this path
      const taggedPathItem = this.addServiceTagToPathItem(pathItem, service.name);

      taggedPathItem.servers = [
        {
          url: serviceExternalUrl,
          description: `${service.name} - ${service.description || 'API Server'}`,
        },
      ];

      aggregated.paths[finalPath] = taggedPathItem;
    }

    // Merge components
    if (spec.components) {
      if (spec.components.schemas) {
        aggregated.components!.schemas = {
          ...aggregated.components!.schemas,
          ...this.prefixComponentKeys(spec.components.schemas, service.name),
        };
      }

      if (spec.components.responses) {
        aggregated.components!.responses = {
          ...aggregated.components!.responses,
          ...this.prefixComponentKeys(spec.components.responses, service.name),
        };
      }

      if (spec.components.parameters) {
        aggregated.components!.parameters = {
          ...aggregated.components!.parameters,
          ...this.prefixComponentKeys(spec.components.parameters, service.name),
        };
      }

      if (spec.components.securitySchemes) {
        aggregated.components!.securitySchemes = {
          ...aggregated.components!.securitySchemes,
          ...this.prefixComponentKeys(spec.components.securitySchemes, service.name),
        };
      }
    }

    // Merge tags
    if (spec.tags) {
      const serviceTags = spec.tags.map((tag) => ({
        ...tag,
        name: `${service.name} - ${tag.name}`,
      }));
      aggregated.tags = [...(aggregated.tags || []), ...serviceTags];
    }

    // Add service tag if not present
    const serviceTag = {
      name: service.name,
      description: service.description,
    };

    if (!aggregated.tags?.some((tag) => tag.name === service.name)) {
      aggregated.tags = [...(aggregated.tags || []), serviceTag];
    }

    const serviceServer = {
      url: serviceExternalUrl,
      description: `${service.name} - ${service.description || 'API Server'}`,
    };

    if (!aggregated.servers) {
      aggregated.servers = [];
    }

    const existingServer = aggregated.servers.find((s) => s.url === serviceExternalUrl);
    if (!existingServer) {
      aggregated.servers.push(serviceServer);
    }

    if (spec?.servers?.length) {
      for (const server of spec.servers) {
        const serverExternalUrl = this.convertToExternalUrl(server.url);
        if (serverExternalUrl !== serviceExternalUrl) {
          const serviceServerFromSpec = {
            url: serverExternalUrl,
            description: `${service.name} - ${server.description || 'Additional Server'}`,
          };

          const alreadyAdded = aggregated.servers.some((s) => s.url === serverExternalUrl);
          if (!alreadyAdded) {
            aggregated.servers.push(serviceServerFromSpec);
          }
        }
      }
    }
  }

  /**
   * Add service tag to all operations in a path item
   */
  private addServiceTagToPathItem(pathItem: PathItem, serviceName: string): PathItem {
    const tagged = { ...pathItem };
    const methods = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head'] as const;

    for (const method of methods) {
      if (tagged[method]) {
        tagged[method] = {
          ...tagged[method],
          tags: [serviceName, ...(tagged[method]?.tags || [])],
        };
      }
    }

    return tagged;
  }

  /**
   * Prefix component keys with service name to avoid conflicts
   */
  private prefixComponentKeys<T extends Record<string, unknown>>(
    components: T,
    serviceName: string
  ): T {
    const prefixed = {} as T;
    const prefix = this.sanitizeServiceName(serviceName);

    for (const [key, value] of Object.entries(components)) {
      (prefixed as Record<string, unknown>)[`${prefix}_${key}`] = value;
    }

    return prefixed;
  }

  /**
   * Sanitize service name for use in URLs and component names
   */
  private sanitizeServiceName(name: string): string {
    return name
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '');
  }

  private convertToExternalUrl(internalUrl: string): string {
    if (internalUrl.includes('localhost') || internalUrl.includes('127.0.0.1')) {
      return internalUrl;
    }

    const servicePortMap: Record<string, number> = {
      'auth-service': 5001,
    };

    try {
      const url = new URL(internalUrl);
      const hostname = url.hostname;

      for (const [serviceName, externalPort] of Object.entries(servicePortMap)) {
        if (hostname.includes(serviceName) || hostname === serviceName) {
          return `http://localhost:${externalPort}`;
        }
      }

      const internalPort = parseInt(url.port || '5000', 10);
      return `http://localhost:${internalPort}`;
    } catch {
      return internalUrl;
    }
  }

  /**
   * Get empty spec template
   */
  private getEmptySpec(): AggregatedSpec {
    return {
      openapi: '3.0.0',
      info: {
        title: config.appName,
        version: config.appVersion,
        description: 'No services available',
      },
      servers: [],
      paths: {},
      'x-services': [],
    };
  }

  /**
   * Get spec for a single service (without aggregation)
   */
  getSingleServiceSpec(service: ServiceConfig, spec: OpenAPISpec): OpenAPISpec {
    return {
      ...spec,
      info: {
        ...spec.info,
        title: `${service.name} - ${spec.info.title}`,
      },
    };
  }
}
