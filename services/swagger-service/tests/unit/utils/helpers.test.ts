/**
 * Unit tests for helper functions
 */
import {
  addPathPrefix,
  deepMerge,
  getUptime,
  getMemoryUsage,
  formatDuration,
  safeJsonParse,
} from '../../../src/utils/helpers';
import { PathItem } from '../../../src/types/openapi.types';

describe('Helper Functions', () => {
  describe('addPathPrefix', () => {
    it('should add prefix to all paths', () => {
      const paths: Record<string, PathItem> = {
        '/users': {
          get: {
            summary: 'Get users',
            responses: { '200': { description: 'Success' } },
          },
        },
        '/posts': {
          get: {
            summary: 'Get posts',
            responses: { '200': { description: 'Success' } },
          },
        },
      };

      const result = addPathPrefix(paths, '/api/v1');

      expect(result).toHaveProperty('/api/v1/users');
      expect(result).toHaveProperty('/api/v1/posts');
      expect(result['/api/v1/users']).toEqual(paths['/users']);
      expect(result['/api/v1/posts']).toEqual(paths['/posts']);
    });

    it('should handle empty paths object', () => {
      const paths: Record<string, PathItem> = {};

      const result = addPathPrefix(paths, '/api');

      expect(result).toEqual({});
    });

    it('should handle single path', () => {
      const paths: Record<string, PathItem> = {
        '/health': {
          get: {
            summary: 'Health check',
            responses: { '200': { description: 'OK' } },
          },
        },
      };

      const result = addPathPrefix(paths, '/v1');

      expect(result).toHaveProperty('/v1/health');
      expect(result['/v1/health']).toEqual(paths['/health']);
    });

    it('should handle prefix with trailing slash', () => {
      const paths: Record<string, PathItem> = {
        '/test': {
          get: {
            responses: { '200': { description: 'OK' } },
          },
        },
      };

      const result = addPathPrefix(paths, '/api/');

      expect(result).toHaveProperty('/api//test');
    });

    it('should preserve path item structure', () => {
      const paths: Record<string, PathItem> = {
        '/users': {
          get: {
            summary: 'Get users',
            parameters: [{ name: 'id', in: 'query' }],
            responses: { '200': { description: 'Success' } },
          },
          post: {
            summary: 'Create user',
            responses: { '201': { description: 'Created' } },
          },
        },
      };

      const result = addPathPrefix(paths, '/api');

      expect(result['/api/users']).toEqual(paths['/users']);
      expect(result['/api/users'].get).toBeDefined();
      expect(result['/api/users'].post).toBeDefined();
    });
  });

  describe('deepMerge', () => {
    it('should merge simple objects', () => {
      const target = { a: 1, b: 2 };
      const source = { b: 3, c: 4 };

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 1, b: 3, c: 4 });
      expect(result).not.toBe(target); // Should return new object
    });

    it('should deep merge nested objects', () => {
      const target: Record<string, unknown> = {
        a: 1,
        nested: {
          x: 10,
          y: 20,
        },
      };
      const source: Record<string, unknown> = {
        nested: {
          y: 30,
          z: 40,
        },
      };

      const result = deepMerge(target, source);

      expect(result).toEqual({
        a: 1,
        nested: {
          x: 10,
          y: 30,
          z: 40,
        },
      });
    });

    it('should handle deeply nested objects', () => {
      const target: Record<string, unknown> = {
        level1: {
          level2: {
            level3: {
              value: 'original',
            },
          },
        },
      };
      const source: Record<string, unknown> = {
        level1: {
          level2: {
            level3: {
              newValue: 'new',
            },
          },
        },
      };

      const result = deepMerge(target, source);

      expect((result.level1 as Record<string, unknown>).level2 as Record<string, unknown>).toBeDefined();
      const level3 = ((result.level1 as Record<string, unknown>).level2 as Record<string, unknown>).level3 as Record<string, unknown>;
      expect(level3.value).toBe('original');
      expect(level3.newValue).toBe('new');
    });

    it('should add new keys from source', () => {
      const target: Record<string, unknown> = { a: 1 };
      const source: Record<string, unknown> = { b: 2, c: 3 };

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 1, b: 2, c: 3 });
    });

    it('should overwrite primitive values', () => {
      const target: Record<string, unknown> = { a: 1, b: 'original', c: true };
      const source: Record<string, unknown> = { a: 2, b: 'updated', c: false };

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 2, b: 'updated', c: false });
    });

    it('should handle empty target', () => {
      const target: Record<string, unknown> = {};
      const source: Record<string, unknown> = { a: 1, b: 2 };

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 1, b: 2 });
    });

    it('should handle empty source', () => {
      const target: Record<string, unknown> = { a: 1, b: 2 };
      const source: Record<string, unknown> = {};

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 1, b: 2 });
    });

    it('should not mutate original target', () => {
      const target: Record<string, unknown> = {
        a: 1,
        nested: { x: 10 },
      };
      const source: Record<string, unknown> = {
        nested: { y: 20 },
      };

      deepMerge(target, source);

      expect(target).toEqual({ a: 1, nested: { x: 10 } });
    });

    it('should handle arrays as primitive values (not deep merge)', () => {
      const target: Record<string, unknown> = { items: [1, 2, 3] };
      const source: Record<string, unknown> = { items: [4, 5, 6] };

      const result = deepMerge(target, source);

      expect(result.items).toEqual([4, 5, 6]);
    });

    it('should handle null values', () => {
      const target: Record<string, unknown> = {
        a: 1,
        b: null,
      };
      const source: Record<string, unknown> = {
        b: 2,
        c: null,
      };

      const result = deepMerge(target, source);

      expect(result).toEqual({ a: 1, b: 2, c: null });
    });
  });

  describe('getUptime', () => {
    it('should return uptime in seconds', () => {
      const uptime = getUptime();

      expect(typeof uptime).toBe('number');
      expect(uptime).toBeGreaterThanOrEqual(0);
    });

    it('should return increasing values over time', async () => {
      const uptime1 = getUptime();
      await new Promise((resolve) => setTimeout(resolve, 1100));
      const uptime2 = getUptime();

      expect(uptime2).toBeGreaterThanOrEqual(uptime1);
    });

    it('should return integer value', () => {
      const uptime = getUptime();

      expect(Number.isInteger(uptime)).toBe(true);
    });
  });

  describe('getMemoryUsage', () => {
    it('should return memory usage object', () => {
      const memory = getMemoryUsage();

      expect(memory).toHaveProperty('used');
      expect(memory).toHaveProperty('total');
      expect(memory).toHaveProperty('percentage');
    });

    it('should return memory in MB', () => {
      const memory = getMemoryUsage();

      expect(typeof memory.used).toBe('number');
      expect(typeof memory.total).toBe('number');
      expect(memory.used).toBeGreaterThan(0);
      expect(memory.total).toBeGreaterThan(0);
    });

    it('should calculate percentage correctly', () => {
      const memory = getMemoryUsage();

      expect(memory.percentage).toBeGreaterThanOrEqual(0);
      expect(memory.percentage).toBeLessThanOrEqual(100);
      expect(memory.percentage).toBe(Math.round((memory.used / memory.total) * 100));
    });

    it('should return rounded values', () => {
      const memory = getMemoryUsage();

      expect(Number.isInteger(memory.used)).toBe(true);
      expect(Number.isInteger(memory.total)).toBe(true);
      expect(Number.isInteger(memory.percentage)).toBe(true);
    });

    it('should have used less than or equal to total', () => {
      const memory = getMemoryUsage();

      expect(memory.used).toBeLessThanOrEqual(memory.total);
    });
  });

  describe('formatDuration', () => {
    it('should format milliseconds', () => {
      expect(formatDuration(500)).toBe('500ms');
      expect(formatDuration(999)).toBe('999ms');
    });

    it('should format seconds', () => {
      expect(formatDuration(1000)).toBe('1s');
      expect(formatDuration(5000)).toBe('5s');
      expect(formatDuration(59000)).toBe('59s');
    });

    it('should format minutes and seconds', () => {
      expect(formatDuration(60000)).toBe('1m 0s');
      expect(formatDuration(125000)).toBe('2m 5s');
      expect(formatDuration(3661000)).toBe('61m 1s');
    });

    it('should handle zero', () => {
      expect(formatDuration(0)).toBe('0ms');
    });

    it('should handle very small values', () => {
      expect(formatDuration(1)).toBe('1ms');
      expect(formatDuration(50)).toBe('50ms');
    });

    it('should handle large values', () => {
      const result = formatDuration(3600000); // 1 hour
      expect(result).toContain('m');
      expect(result).toContain('s');
    });

    it('should round down seconds correctly', () => {
      expect(formatDuration(1599)).toBe('1s'); // Should round down, not up
      expect(formatDuration(59999)).toBe('59s');
    });
  });

  describe('safeJsonParse', () => {
    it('should parse valid JSON', () => {
      const json = '{"name": "test", "value": 123}';
      const fallback = {};

      const result = safeJsonParse(json, fallback);

      expect(result).toEqual({ name: 'test', value: 123 });
    });

    it('should return fallback for invalid JSON', () => {
      const json = 'invalid json';
      const fallback = { error: 'parse failed' };

      const result = safeJsonParse(json, fallback);

      expect(result).toBe(fallback);
    });

    it('should return fallback for empty string', () => {
      const json = '';
      const fallback = null;

      const result = safeJsonParse(json, fallback);

      expect(result).toBe(fallback);
    });

    it('should return fallback for malformed JSON', () => {
      const json = '{name: "test"}'; // Missing quotes
      const fallback = {};

      const result = safeJsonParse(json, fallback);

      expect(result).toBe(fallback);
    });

    it('should parse arrays', () => {
      const json = '[1, 2, 3]';
      const fallback: number[] = [];

      const result = safeJsonParse(json, fallback);

      expect(result).toEqual([1, 2, 3]);
    });

    it('should parse numbers', () => {
      const json = '42';
      const fallback = 0;

      const result = safeJsonParse(json, fallback);

      expect(result).toBe(42);
    });

    it('should parse strings', () => {
      const json = '"hello world"';
      const fallback = '';

      const result = safeJsonParse(json, fallback);

      expect(result).toBe('hello world');
    });

    it('should parse booleans', () => {
      const json = 'true';
      const fallback = false;

      const result = safeJsonParse(json, fallback);

      expect(result).toBe(true);
    });

    it('should parse null', () => {
      const json = 'null';
      const fallback = {};

      const result = safeJsonParse(json, fallback);

      expect(result).toBeNull();
    });

    it('should handle nested objects', () => {
      const json = '{"level1": {"level2": {"value": 123}}}';
      const fallback = {};

      const result = safeJsonParse(json, fallback);

      expect(result).toEqual({ level1: { level2: { value: 123 } } });
    });
  });
});

