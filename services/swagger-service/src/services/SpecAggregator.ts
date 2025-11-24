/**
 * OpenAPI specification aggregator
 */
import { OpenAPISpec, AggregatedSpec, PathItem } from '../types/openapi.types';
import { ServiceConfig } from '../types/service.types';
import logger from '../utils/logger';
import config from '../config/environment';

/**
 * Type for values that can contain schema references
 * This is a recursive type that matches any JSON-serializable structure
 */
type SchemaReferenceValue = unknown;

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
    const componentPrefix = this.sanitizeServiceName(service.name);

    for (const [path, pathItem] of Object.entries(spec.paths)) {
      // Always prefix paths with service name to avoid conflicts
      const finalPath = `${pathPrefix}${path}`;

      // Add service tag to all operations in this path
      const taggedPathItem = this.addServiceTagToPathItem(pathItem, service.name);

      // Update schema references in the path item to use prefixed names
      const updatedPathItem = this.updateSchemaReferences(
        taggedPathItem,
        componentPrefix
      ) as PathItem;

      // Debug logging
      if (path === '/v1/auth/register') {
        const requestBody = taggedPathItem?.post?.requestBody;
        const updatedRequestBody = updatedPathItem?.post?.requestBody;
        const originalSchema =
          requestBody &&
          !('$ref' in requestBody) &&
          requestBody.content?.['application/json']?.schema;
        const updatedSchema =
          updatedRequestBody &&
          !('$ref' in updatedRequestBody) &&
          updatedRequestBody.content?.['application/json']?.schema;
        logger.info(`Updating schema refs for ${path}:`, {
          componentPrefix,
          original: JSON.stringify(originalSchema),
          updated: JSON.stringify(updatedSchema),
        });
      }

      updatedPathItem.servers = [
        {
          url: serviceExternalUrl,
          description: `${service.name} - ${service.description || 'API Server'}`,
        },
      ];

      aggregated.paths[finalPath] = updatedPathItem;
    }

    // Merge components
    if (spec.components) {
      const componentPrefix = this.sanitizeServiceName(service.name);

      if (spec.components.schemas) {
        // Prefix the schema keys and update internal references
        const prefixedSchemas = this.prefixComponentKeys(spec.components.schemas, service.name);
        // Update any internal schema references within the schemas themselves
        const updatedSchemas = this.updateSchemaReferences(
          prefixedSchemas,
          componentPrefix
        ) as typeof prefixedSchemas;
        aggregated.components!.schemas = {
          ...aggregated.components!.schemas,
          ...updatedSchemas,
        };
      }

      if (spec.components.responses) {
        const prefixedResponses = this.prefixComponentKeys(spec.components.responses, service.name);
        const updatedResponses = this.updateSchemaReferences(
          prefixedResponses,
          componentPrefix
        ) as typeof prefixedResponses;
        aggregated.components!.responses = {
          ...aggregated.components!.responses,
          ...updatedResponses,
        };
      }

      if (spec.components.parameters) {
        const prefixedParameters = this.prefixComponentKeys(
          spec.components.parameters,
          service.name
        );
        const updatedParameters = this.updateSchemaReferences(
          prefixedParameters,
          componentPrefix
        ) as typeof prefixedParameters;
        aggregated.components!.parameters = {
          ...aggregated.components!.parameters,
          ...updatedParameters,
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
   * Update schema references in a path item to use prefixed component names
   */
  private updateSchemaReferences<T extends SchemaReferenceValue>(obj: T, prefix: string): T {
    if (!obj) return obj;

    // Handle string references
    if (typeof obj === 'string' && obj.startsWith('#/components/schemas/')) {
      const schemaName = obj.replace('#/components/schemas/', '');
      return `#/components/schemas/${prefix}_${schemaName}` as T;
    }

    // Handle arrays
    if (Array.isArray(obj)) {
      return obj.map((item) => this.updateSchemaReferences(item, prefix)) as T;
    }

    // Handle objects
    if (typeof obj === 'object' && obj !== null) {
      const updated: Record<string, SchemaReferenceValue> = {};
      for (const [key, value] of Object.entries(obj)) {
        if (
          key === '$ref' &&
          typeof value === 'string' &&
          value.startsWith('#/components/schemas/')
        ) {
          const schemaName = value.replace('#/components/schemas/', '');
          updated[key] = `#/components/schemas/${prefix}_${schemaName}`;
        } else {
          updated[key] = this.updateSchemaReferences(value as SchemaReferenceValue, prefix);
        }
      }
      return updated as T;
    }

    return obj;
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
      'user-service': 5002,
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
