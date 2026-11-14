/** Build the same source in normal-server and standalone packaging modes. */
const reference = process.env.OCI_KIT_REFERENCE === '1';
const config = {
  output: reference ? undefined : 'standalone',
  distDir: reference ? '.next/reference' : '.next',
  outputFileTracingRoot: import.meta.dirname,
  poweredByHeader: false,
  async redirects() {
    return [{ source: '/start', destination: '/checklist/idea', permanent: false }];
  },
};

export default config;
