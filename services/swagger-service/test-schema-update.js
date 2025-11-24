const { SpecAggregator } = require('./dist/services/SpecAggregator');

// Create an instance of SpecAggregator
const aggregator = new SpecAggregator();

// Test data
const testPathItem = {
  post: {
    requestBody: {
      content: {
        'application/json': {
          schema: {
            '$ref': '#/components/schemas/RegisterRequest'
          }
        }
      }
    }
  }
};

// Test the updateSchemaReferences method
const updated = aggregator.updateSchemaReferences(testPathItem, 'account-service');

console.log('Original schema ref:', testPathItem.post.requestBody.content['application/json'].schema);
console.log('Updated schema ref:', updated.post.requestBody.content['application/json'].schema);
console.log('Expected: #/components/schemas/account-service_RegisterRequest');
