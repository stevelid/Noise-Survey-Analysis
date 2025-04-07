// vitest.config.js
export default {
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['**/*.{test,spec}.{js,ts,jsx,tsx}'],
    exclude: ['node_modules', 'dist', '.idea', '.git', '.cache'],
    environmentOptions: {
      jsdom: {
        // jsdom options here
      }
    }
  }
}; 