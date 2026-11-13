import { defineConfig } from 'astro/config';

// Override these public build settings for a custom domain or preview host.
export default defineConfig({
  site: process.env.SITE_URL || 'https://karthiksuku.github.io',
  base: process.env.SITE_BASE || '/oci-founder-kit/',
  output: 'static',
  trailingSlash: 'always',
  build: { format: 'directory' },
  devToolbar: { enabled: false },
});
