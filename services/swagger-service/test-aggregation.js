const { SpecAggregator } = require('./dist/services/SpecAggregator');
const fs = require('fs');

// Create an instance of SpecAggregator
const aggregator = new SpecAggregator();

// Load mock spec
const authSpec = JSON.parse(fs.readFileSync('./mock-specs/auth-service.json', 'utf8'));

// Create service config
const serviceConfig = {
  name: 'Account Service',
  url: 'http://auth-service:5000',
  description: 'User authentication and account management service'
};

// Test the mergeSpecs method
const aggregatedSpec = aggregator.mergeSpecs([{ service: serviceConfig, spec: authSpec }]);

// Check if schema references are updated
const registerPath = aggregatedSpec.paths['/v1/auth/register'];
const schemaRef = registerPath?.post?.requestBody?.content?.['application/json']?.schema?.['$ref'];

console.log('Aggregated spec paths:', Object.keys(aggregatedSpec.paths));
console.log('Schema reference in /v1/auth/register:', schemaRef);
console.log('Expected: #/components/schemas/account-service_RegisterRequest');
console.log('Match:', schemaRef === '#/components/schemas/account-service_RegisterRequest');

// Check if schemas are prefixed
console.log('\nAvailable schemas:', Object.keys(aggregatedSpec.components.schemas));

// Save the aggregated spec for inspection
fs.writeFileSync('./test-aggregated-spec.json', JSON.stringify(aggregatedSpec, null, 2));
console.log('\nAggregated spec saved to test-aggregated-spec.json');
