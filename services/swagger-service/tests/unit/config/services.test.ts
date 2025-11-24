/**
 * Unit tests for services configuration
 */
import services, { services as namedExport } from '../../../src/config/services';
import config from '../../../src/config/environment';

jest.mock('../../../src/config/environment', () => ({
  accountServiceUrl: 'http://localhost:5000',
  userServiceUrl: 'http://localhost:5001',
}));

describe('Services Configuration', () => {
  it('should export services array', () => {
    expect(services).toBeDefined();
    expect(Array.isArray(services)).toBe(true);
  });

  it('should export named export', () => {
    expect(namedExport).toBeDefined();
    expect(namedExport).toBe(services);
  });

  it('should have Account Service configured', () => {
    const accountService = services.find((s) => s.name === 'Account Service');

    expect(accountService).toBeDefined();
    expect(accountService?.url).toBe(config.accountServiceUrl);
    expect(accountService?.specEndpoint).toBe('/openapi.json');
    expect(accountService?.healthEndpoint).toBe('/health');
    expect(accountService?.description).toBe('User authentication and account management service');
    expect(accountService?.version).toBe('1.0.0');
    expect(accountService?.enabled).toBe(true);
  });

  it('should have User Service configured', () => {
    const userService = services.find((s) => s.name === 'User Service');

    expect(userService).toBeDefined();
    expect(userService?.url).toBe(config.userServiceUrl);
    expect(userService?.specEndpoint).toBe('/openapi.json');
    expect(userService?.healthEndpoint).toBe('/health');
    expect(userService?.description).toBe('User profile management service');
    expect(userService?.version).toBe('1.0.0');
    expect(userService?.enabled).toBe(true);
  });

  it('should have tags for Account Service', () => {
    const accountService = services.find((s) => s.name === 'Account Service');

    expect(accountService?.tags).toContain('authentication');
    expect(accountService?.tags).toContain('users');
    expect(accountService?.tags).toContain('security');
  });

  it('should have tags for User Service', () => {
    const userService = services.find((s) => s.name === 'User Service');

    expect(userService?.tags).toContain('users');
    expect(userService?.tags).toContain('profiles');
    expect(userService?.tags).toContain('management');
  });

  it('should have all services enabled by default', () => {
    services.forEach((service) => {
      expect(service.enabled).toBe(true);
    });
  });

  it('should have required fields for all services', () => {
    services.forEach((service) => {
      expect(service.name).toBeDefined();
      expect(service.url).toBeDefined();
      expect(service.specEndpoint).toBeDefined();
      expect(service.healthEndpoint).toBeDefined();
      expect(service.description).toBeDefined();
      expect(service.version).toBeDefined();
      expect(service.enabled).toBeDefined();
    });
  });
});

