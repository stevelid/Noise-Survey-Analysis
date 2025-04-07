// vitest.config.js
export default {
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['**/*.{test,spec}.{js,ts,jsx,tsx}'],
    exclude: ['node_modules', 'dist', '.idea', '.git', '.cache'],
    environmentOptions: {
      jsdom: {
        // Custom jsdom options
        url: 'http://localhost',
        // Add any other JSDOM-specific options here if needed
      }
    },
    // Setup global mocks, if needed
    setupFiles: [
      // Reference our setup file for shared test utilities
      './tests/js/setup.js'
    ],
    // Configure code coverage if needed
    coverage: {
      provider: 'v8', // or 'istanbul'
      reporter: ['text', 'html', 'json'],
      exclude: [
        'node_modules/**',
        'test/**',
        '**/*.d.ts',
        '**/*.test.{js,ts}',
        '**/*.spec.{js,ts}'
      ]
    },
    // Specific test environment variables
    env: {
      NODE_ENV: 'test'
    }
  }
}; 