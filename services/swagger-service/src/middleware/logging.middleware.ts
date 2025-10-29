/**
 * Logging middleware for HTTP requests
 */
import { Request, Response, NextFunction } from 'express';
import logger from '../utils/logger';

export function loggingMiddleware(req: Request, res: Response, next: NextFunction): void {
  const startTime = Date.now();

  // Log request
  logger.http(`${req.method} ${req.path}`);

  // Log response when finished
  res.on('finish', () => {
    const duration = Date.now() - startTime;
    const level = res.statusCode >= 400 ? 'warn' : 'http';

    logger.log(level, `${req.method} ${req.path} ${res.statusCode} - ${duration}ms`);
  });

  next();
}
