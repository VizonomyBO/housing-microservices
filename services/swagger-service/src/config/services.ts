/**
 * Service registry configuration
 */
import { ServiceConfig } from '../types/service.types';
import config from './environment';

export const services: ServiceConfig[] = [
  {
    name: 'Account Service',
    url: config.accountServiceUrl,
    specEndpoint: '/openapi.json',
    healthEndpoint: '/health',
    description: 'User authentication and account management service',
    version: '1.0.0',
    tags: ['authentication', 'users', 'security'],
    enabled: true,
  },
  {
    name: 'User Service',
    url: config.userServiceUrl,
    specEndpoint: '/openapi.json',
    healthEndpoint: '/v1/health',
    description: 'User profile management service',
    version: '1.0.0',
    tags: ['users', 'profiles', 'management'],
    enabled: true,
  },
];

export default services;
