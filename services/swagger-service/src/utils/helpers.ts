/**
 * Utility helper functions
 */

import { PathItem } from '../types/openapi.types';

/**
 * Add a path prefix to all paths in an OpenAPI spec
 */
export function addPathPrefix(
  paths: Record<string, PathItem>,
  prefix: string
): Record<string, PathItem> {
  const prefixedPaths: Record<string, PathItem> = {};

  for (const [path, pathItem] of Object.entries(paths)) {
    const newPath = `${prefix}${path}`;
    prefixedPaths[newPath] = pathItem;
  }

  return prefixedPaths;
}

/**
 * Deep merge two objects
 */
export function deepMerge<T extends Record<string, unknown>>(target: T, source: Partial<T>): T {
  const output = { ...target } as T;

  if (isObject(target) && isObject(source)) {
    Object.keys(source).forEach((key) => {
      const typedKey = key as keyof T;
      if (isObject(source[typedKey])) {
        if (!(key in target)) {
          (output as Record<string, unknown>)[key] = source[typedKey];
        } else {
          output[typedKey] = deepMerge(
            target[typedKey] as Record<string, unknown>,
            source[typedKey] as Partial<Record<string, unknown>>
          ) as T[keyof T];
        }
      } else {
        (output as Record<string, unknown>)[key] = source[typedKey];
      }
    });
  }

  return output;
}

/**
 * Check if a value is an object
 */
function isObject(item: unknown): item is Record<string, unknown> {
  return item !== null && typeof item === 'object' && !Array.isArray(item);
}

/**
 * Calculate uptime in seconds
 */
const startTime = Date.now();

export function getUptime(): number {
  return Math.floor((Date.now() - startTime) / 1000);
}

/**
 * Get memory usage information
 */
export function getMemoryUsage(): { used: number; total: number; percentage: number } {
  const used = process.memoryUsage().heapUsed;
  const total = process.memoryUsage().heapTotal;

  return {
    used: Math.round(used / 1024 / 1024), // MB
    total: Math.round(total / 1024 / 1024), // MB
    percentage: Math.round((used / total) * 100),
  };
}

/**
 * Format duration in milliseconds to human-readable string
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }

  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

/**
 * Safe JSON parse with error handling
 */
export function safeJsonParse<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json);
  } catch {
    return fallback;
  }
}
