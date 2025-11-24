/**
 * Unit tests for error handling middleware
 */
import request from 'supertest';
import express, { Express, Request, Response, NextFunction } from 'express';
import { errorHandler, notFoundHandler, ApiError } from '../../../src/middleware/error.middleware';
import logger from '../../../src/utils/logger';

// Mock logger
jest.mock('../../../src/utils/logger', () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  http: jest.fn(),
  log: jest.fn(),
}));

describe('Error Middleware', () => {
  let app: Express;

  beforeEach(() => {
    jest.clearAllMocks();
    app = express();
  });

  describe('errorHandler', () => {
    it('should handle errors with status code', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        const error: ApiError = new Error('Test error');
        error.statusCode = 400;
        next(error);
      });
      app.use(errorHandler);

      const response = await request(app).get('/error');

      expect(response.status).toBe(400);
      expect(response.body.error).toBeDefined();
      expect(response.body.error.message).toBe('Test error');
      expect(response.body.error.status).toBe(400);
      expect(response.body.error.path).toBe('/error');
      expect(response.body.error.timestamp).toBeDefined();
    });

    it('should default to 500 for errors without status code', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        next(new Error('Test error'));
      });
      app.use(errorHandler);

      const response = await request(app).get('/error');

      expect(response.status).toBe(500);
      expect(response.body.error.status).toBe(500);
    });

    it('should use default message for errors without message', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        const error = new Error();
        error.message = '';
        next(error);
      });
      app.use(errorHandler);

      const response = await request(app).get('/error');

      expect(response.body.error.message).toBe('Internal server error');
    });

    it('should log error with stack trace', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        const error = new Error('Test error');
        error.stack = 'Error stack trace';
        next(error);
      });
      app.use(errorHandler);

      await request(app).get('/error');

      expect(logger.error).toHaveBeenCalledWith(
        expect.stringContaining('Test error')
      );
      expect(logger.error).toHaveBeenCalledWith('Error stack trace');
    });

    it('should log error without stack trace if not available', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        const error = new Error('Test error');
        delete (error as any).stack;
        next(error);
      });
      app.use(errorHandler);

      await request(app).get('/error');

      expect(logger.error).toHaveBeenCalled();
    });

    it('should include path in error response', async () => {
      app.get('/custom-path', (_req: Request, _res: Response, next: NextFunction) => {
        const error: ApiError = new Error('Test error');
        error.statusCode = 404;
        next(error);
      });
      app.use(errorHandler);

      const response = await request(app).get('/custom-path');

      expect(response.body.error.path).toBe('/custom-path');
    });

    it('should handle operational errors', async () => {
      app.get('/error', (_req: Request, _res: Response, next: NextFunction) => {
        const error: ApiError = new Error('Operational error');
        error.statusCode = 400;
        error.isOperational = true;
        next(error);
      });
      app.use(errorHandler);

      const response = await request(app).get('/error');

      expect(response.status).toBe(400);
      expect(response.body.error.message).toBe('Operational error');
    });
  });

  describe('notFoundHandler', () => {
    it('should return 404 for non-existent routes', async () => {
      app.get('/exists', (_req, res) => {
        res.json({ message: 'exists' });
      });
      app.use(notFoundHandler);

      const response = await request(app).get('/non-existent');

      expect(response.status).toBe(404);
      expect(response.body.error).toBeDefined();
      expect(response.body.error.message).toBe('Resource not found');
      expect(response.body.error.status).toBe(404);
      expect(response.body.error.path).toBe('/non-existent');
      expect(response.body.error.timestamp).toBeDefined();
    });

    it('should include correct path in 404 response', async () => {
      app.use(notFoundHandler);

      const response = await request(app).get('/another/missing/path');

      expect(response.body.error.path).toBe('/another/missing/path');
    });

    it('should include timestamp in 404 response', async () => {
      app.use(notFoundHandler);

      const response = await request(app).get('/test');

      expect(response.body.error.timestamp).toBeDefined();
      expect(new Date(response.body.error.timestamp).getTime()).toBeGreaterThan(0);
    });
  });
});

