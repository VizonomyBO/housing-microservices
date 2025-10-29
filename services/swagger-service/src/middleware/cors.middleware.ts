/**
 * CORS middleware configuration
 */
import cors from 'cors';
import config from '../config/environment';

export const corsMiddleware = cors({
  origin: config.corsOrigins,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true,
  maxAge: 86400, // 24 hours
});
