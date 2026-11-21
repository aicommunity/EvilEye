import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const deps = fileURLToPath(new URL('../../evileye/api/frontend/node_modules/', import.meta.url));
export default {
  root,
  resolve: { alias: {
    react: `${deps}/react`,
    'react-test-renderer': `${deps}/react-test-renderer`,
    vitest: `${deps}/vitest/dist/index.js`,
  } },
  test: { environment: 'node', include: ['reports/audit_dcfc98dd/frontend_probes.test.ts'],
    pool: 'forks', maxWorkers: 1, minWorkers: 1, testTimeout: 10000 },
};
