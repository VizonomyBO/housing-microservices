/**
 * Error handling middleware
 */
import { Request, Response, NextFunction } from 'express';
import logger from '../utils/logger';

export interface ApiError extends Error {
  statusCode?: number;
  isOperational?: boolean;
}

export function errorHandler(
  error: ApiError,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  const statusCode = error.statusCode || 500;
  const message = error.message || 'Internal server error';

  logger.error(`Error: ${message} - ${req.method} ${req.path}`);

  if (error.stack) {
    logger.error(error.stack);
  }

  res.status(statusCode).json({
    error: {
      message,
      status: statusCode,
      path: req.path,
      timestamp: new Date().toISOString(),
    },
  });
}

export function notFoundHandler(req: Request, res: Response): void {
  res.status(404).json({
    error: {
      message: 'Resource not found',
      status: 404,
      path: req.path,
      timestamp: new Date().toISOString(),
    },
  });
}
