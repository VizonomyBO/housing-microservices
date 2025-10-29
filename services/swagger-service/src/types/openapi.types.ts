/**
 * OpenAPI specification types
 */

/**
 * OpenAPI Schema Object (simplified - can represent complex JSON Schema)
 */
export type Schema = Record<string, unknown>;

/**
 * OpenAPI Parameter Object
 */
export interface Parameter {
  name: string;
  in: 'query' | 'header' | 'path' | 'cookie';
  description?: string;
  required?: boolean;
  deprecated?: boolean;
  allowEmptyValue?: boolean;
  style?: string;
  explode?: boolean;
  allowReserved?: boolean;
  schema?: Schema;
  example?: unknown;
  examples?: Record<string, unknown>;
  content?: Record<string, { schema?: Schema }>;
}

/**
 * OpenAPI Reference Object
 */
export interface Reference {
  $ref: string;
}

/**
 * OpenAPI Response Object
 */
export interface Response {
  description: string;
  headers?: Record<string, Header | Reference>;
  content?: Record<string, MediaType>;
  links?: Record<string, Link | Reference>;
}

/**
 * OpenAPI MediaType Object
 */
export interface MediaType {
  schema?: Schema | Reference;
  example?: unknown;
  examples?: Record<string, unknown>;
  encoding?: Record<string, Encoding>;
}

/**
 * OpenAPI Encoding Object
 */
export interface Encoding {
  contentType?: string;
  headers?: Record<string, Header | Reference>;
  style?: string;
  explode?: boolean;
  allowReserved?: boolean;
}

/**
 * OpenAPI Header Object
 */
export interface Header {
  description?: string;
  required?: boolean;
  deprecated?: boolean;
  allowEmptyValue?: boolean;
  style?: string;
  explode?: boolean;
  allowReserved?: boolean;
  schema?: Schema;
  example?: unknown;
  examples?: Record<string, unknown>;
  content?: Record<string, MediaType>;
}

/**
 * OpenAPI RequestBody Object
 */
export interface RequestBody {
  description?: string;
  content: Record<string, MediaType>;
  required?: boolean;
}

/**
 * OpenAPI SecurityScheme Object
 */
export interface SecurityScheme {
  type: 'apiKey' | 'http' | 'oauth2' | 'openIdConnect';
  description?: string;
  name?: string;
  in?: 'query' | 'header' | 'cookie';
  scheme?: string;
  bearerFormat?: string;
  flows?: OAuthFlows;
  openIdConnectUrl?: string;
}

/**
 * OpenAPI OAuthFlows Object
 */
export interface OAuthFlows {
  implicit?: OAuthFlow;
  password?: OAuthFlow;
  clientCredentials?: OAuthFlow;
  authorizationCode?: OAuthFlow;
}

/**
 * OpenAPI OAuthFlow Object
 */
export interface OAuthFlow {
  authorizationUrl?: string;
  tokenUrl?: string;
  refreshUrl?: string;
  scopes: Record<string, string>;
}

/**
 * OpenAPI Example Object
 */
export type Example = Record<string, unknown>;

/**
 * OpenAPI Link Object
 */
export interface Link {
  operationRef?: string;
  operationId?: string;
  parameters?: Record<string, unknown>;
  requestBody?: unknown;
  description?: string;
  server?: {
    url: string;
    description?: string;
  };
}

/**
 * OpenAPI Callback Object
 */
export type Callback = Record<string, PathItem>;

export interface OpenAPISpec {
  openapi: string;
  info: {
    title: string;
    version: string;
    description?: string;
    contact?: {
      name?: string;
      url?: string;
      email?: string;
    };
    license?: {
      name: string;
      url?: string;
    };
  };
  servers?: Array<{
    url: string;
    description?: string;
  }>;
  paths: {
    [path: string]: PathItem;
  };
  components?: {
    schemas?: { [key: string]: Schema | Reference };
    responses?: { [key: string]: Response | Reference };
    parameters?: { [key: string]: Parameter | Reference };
    examples?: { [key: string]: Example | Reference };
    requestBodies?: { [key: string]: RequestBody | Reference };
    headers?: { [key: string]: Header | Reference };
    securitySchemes?: { [key: string]: SecurityScheme | Reference };
    links?: { [key: string]: Link | Reference };
    callbacks?: { [key: string]: Callback | Reference };
  };
  security?: Array<{ [key: string]: string[] }>;
  tags?: Array<{
    name: string;
    description?: string;
    externalDocs?: {
      description?: string;
      url: string;
    };
  }>;
  externalDocs?: {
    description?: string;
    url: string;
  };
}

export interface PathItem {
  summary?: string;
  description?: string;
  get?: Operation;
  put?: Operation;
  post?: Operation;
  delete?: Operation;
  options?: Operation;
  head?: Operation;
  patch?: Operation;
  trace?: Operation;
  servers?: Array<{ url: string; description?: string }>;
  parameters?: Array<Parameter | Reference>;
}

export interface Operation {
  tags?: string[];
  summary?: string;
  description?: string;
  operationId?: string;
  parameters?: Array<Parameter | Reference>;
  requestBody?: RequestBody | Reference;
  responses: {
    [statusCode: string]: Response | Reference;
  };
  callbacks?: { [key: string]: Callback | Reference };
  deprecated?: boolean;
  security?: Array<{ [key: string]: string[] }>;
  servers?: Array<{ url: string; description?: string }>;
}

export interface AggregatedSpec extends OpenAPISpec {
  'x-services': Array<{
    name: string;
    version: string;
    pathPrefix?: string;
  }>;
}
