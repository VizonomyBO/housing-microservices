const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 5000;  // Correct port for auth-service

// Mock auth-service endpoints
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'auth-service' });
});

app.get('/openapi.json', (req, res) => {
  const spec = JSON.parse(fs.readFileSync(path.join(__dirname, 'mock-specs/auth-service.json'), 'utf8'));
  res.json(spec);
});

// Mock user-service endpoints  
const PORT2 = 5001;  // Correct port for user-service
const app2 = express();

app2.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'user-service' });
});

app2.get('/openapi.json', (req, res) => {
  // Return a simple user-service spec
  res.json({
    openapi: '3.0.0',
    info: { title: 'User Service API', version: '1.0.0' },
    paths: {
      '/v1/users/me': {
        get: {
          summary: 'Get current user',
          responses: {
            '200': { description: 'Success' }
          }
        }
      }
    },
    components: {
      schemas: {
        User: {
          type: 'object',
          properties: {
            id: { type: 'string' },
            email: { type: 'string' }
          }
        }
      }
    }
  });
});

app.listen(PORT, () => {
  console.log(`Mock auth-service running on http://localhost:${PORT}`);
});

app2.listen(PORT2, () => {
  console.log(`Mock user-service running on http://localhost:${PORT2}`);
});
