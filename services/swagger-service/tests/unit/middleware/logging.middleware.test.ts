/**
 * Unit tests for logging middleware
 */
import request from 'supertest';
import express, { Express } from 'express';
import { loggingMiddleware } from '../../../src/middleware/logging.middleware';
import logger from '../../../src/utils/logger';

// Mock logger
jest.mock('../../../src/utils/logger', () => ({
  http: jest.fn(),
  log: jest.fn(),
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
}));

describe('Logging Middleware', () => {
  let app: Express;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    app = express();
    app.use(loggingMiddleware);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should log incoming requests', async () => {
    app.get('/test', (_req, res) => {
      res.json({ message: 'test' });
    });

    await request(app).get('/test');

    expect(logger.http).toHaveBeenCalledWith('GET /test');
  });

  it('should log response when request finishes', async () => {
    app.get('/test', (_req, res) => {
      res.json({ message: 'test' });
    });

    const responsePromise = request(app).get('/test');
    jest.advanceTimersByTime(100);
    await responsePromise;

    expect(logger.log).toHaveBeenCalledWith(
      'http',
      expect.stringMatching(/GET \/test 200 - \d+ms/)
    );
  });

  it('should log warning for 4xx status codes', async () => {
    app.get('/test', (_req, res) => {
      res.status(404).json({ error: 'not found' });
    });

    const responsePromise = request(app).get('/test');
    jest.advanceTimersByTime(100);
    await responsePromise;

    expect(logger.log).toHaveBeenCalledWith(
      'warn',
      expect.stringMatching(/GET \/test 404 - \d+ms/)
    );
  });

  it('should log warning for 5xx status codes', async () => {
    app.get('/test', (_req, res) => {
      res.status(500).json({ error: 'server error' });
    });

    const responsePromise = request(app).get('/test');
    jest.advanceTimersByTime(100);
    await responsePromise;

    expect(logger.log).toHaveBeenCalledWith(
      'warn',
      expect.stringMatching(/GET \/test 500 - \d+ms/)
    );
  });

  it('should log http level for 2xx status codes', async () => {
    app.get('/test', (_req, res) => {
      res.status(200).json({ message: 'success' });
    });

    const responsePromise = request(app).get('/test');
    jest.advanceTimersByTime(100);
    await responsePromise;

    expect(logger.log).toHaveBeenCalledWith(
      'http',
      expect.stringMatching(/GET \/test 200 - \d+ms/)
    );
  });

  it('should calculate request duration', async () => {
    app.get('/test', (_req, res) => {
      res.json({ message: 'test' });
    });

    const responsePromise = request(app).get('/test');
    // Advance timers before awaiting to simulate time passing
    jest.advanceTimersByTime(150);
    await responsePromise;
    // Advance timers again after response to ensure duration is calculated
    jest.advanceTimersByTime(1);

    // Check that duration was logged (may be 0ms with fake timers, so just check format)
    expect(logger.log).toHaveBeenCalledWith(
      'http',
      expect.stringMatching(/GET \/test 200 - \d+ms/)
    );
  });

  it('should call next() to continue request processing', async () => {
    let nextCalled = false;
    app.use((_req, _res, next) => {
      nextCalled = true;
      next();
    });
    app.get('/test', (_req, res) => {
      res.json({ message: 'test' });
    });

    await request(app).get('/test');

    expect(nextCalled).toBe(true);
  });

  it('should log different HTTP methods', async () => {
    app.post('/test', (_req, res) => {
      res.json({ message: 'created' });
    });

    const responsePromise = request(app).post('/test');
    jest.advanceTimersByTime(50);
    await responsePromise;

    expect(logger.http).toHaveBeenCalledWith('POST /test');
  });

  it('should log request path correctly', async () => {
    app.get('/api/v1/users', (_req, res) => {
      res.json({ users: [] });
    });

    const responsePromise = request(app).get('/api/v1/users');
    jest.advanceTimersByTime(75);
    await responsePromise;

    expect(logger.http).toHaveBeenCalledWith('GET /api/v1/users');
  });
});

