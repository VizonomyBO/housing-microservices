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
  // Add more services here as they become available
  // {
  //   name: 'Product Service',
  //   url: 'http://product-service:5001',
  //   specEndpoint: '/openapi.json',
  //   healthEndpoint: '/health',
  //   description: 'Product catalog and inventory management',
  //   version: '1.0.0',
  //   tags: ['products', 'inventory'],
  //   enabled: true,
  // },
];

export default services;
