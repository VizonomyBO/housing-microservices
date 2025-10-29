/**
 * Documentation routes with Swagger UI
 */
import { Router, Request, Response } from 'express';
import swaggerUi from 'swagger-ui-express';
import { ServiceDiscovery } from '../services/ServiceDiscovery';
import { SpecAggregator } from '../services/SpecAggregator';

export function createDocsRoutes(_discovery: ServiceDiscovery, _aggregator: SpecAggregator): Router {
  const router = Router();

  /**
   * Swagger UI setup function
   * Reference the spec via URL so it's always up-to-date
   */
  const swaggerUiOptions = {
    explorer: true,
    swaggerOptions: {
      url: '/api/specs',
      persistAuthorization: true,
      displayRequestDuration: true,
      filter: true,
      syntaxHighlight: {
        activate: true,
        theme: 'monokai',
      },
    },
  };

  /**
   * GET /docs
   * Serve aggregated Swagger UI
   * Mount swagger-ui-express at /docs path
   * swaggerUi.serve handles static assets (CSS, JS files)
   * swaggerUi.setup handles serving the HTML UI
   */
  router.use('/docs', ...swaggerUi.serve, swaggerUi.setup(null, swaggerUiOptions));

  /**
   * GET /
   * Root endpoint - redirect to docs or show landing page
   */
  router.get('/', (_req: Request, res: Response) => {
    res.send(`
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Swagger Aggregator Service</title>
        <style>
          * { margin: 0; padding: 0; box-sizing: border-box; }
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
          }
          .container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 60px;
            max-width: 600px;
            text-align: center;
          }
          h1 {
            color: #333;
            margin-bottom: 16px;
            font-size: 2.5em;
          }
          p {
            color: #666;
            margin-bottom: 32px;
            font-size: 1.1em;
            line-height: 1.6;
          }
          .buttons {
            display: flex;
            gap: 16px;
            justify-content: center;
            flex-wrap: wrap;
          }
          a {
            display: inline-block;
            padding: 14px 32px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
          }
          a:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
            background: #5568d3;
          }
          .secondary {
            background: #764ba2;
            box-shadow: 0 4px 12px rgba(118, 75, 162, 0.4);
          }
          .secondary:hover {
            background: #663a8f;
            box-shadow: 0 6px 20px rgba(118, 75, 162, 0.6);
          }
          .version {
            margin-top: 32px;
            color: #999;
            font-size: 0.9em;
          }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>🚀 Swagger Aggregator</h1>
          <p>
            Centralized API documentation portal for all microservices.
            Explore the unified API documentation or check system status.
          </p>
          <div class="buttons">
            <a href="/docs">View API Documentation</a>
            <a href="/api/status" class="secondary">System Status</a>
          </div>
          <div class="version">Version 1.0.0</div>
        </div>
      </body>
      </html>
    `);
  });

  return router;
}
