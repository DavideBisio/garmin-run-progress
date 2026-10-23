// @ts-check
import { defineConfig } from 'astro/config';
import siteKit from '@davidebisio/site-kit/integration';

export default defineConfig({
  site: 'https://davidebisio.github.io',
  // Project sites are served from /<repo>/. The hub (davidebisio.github.io) uses '/'.
  base: '/garmin-run-progress',
  // docs/roadmap/README.md is published at /docs/roadmap/readme/ like every README (so the
  // kit's .md link rewriting stays right); the folder URL leads there.
  redirects: {
    '/docs/roadmap': '/garmin-run-progress/docs/roadmap/readme/',
  },
  integrations: [
    siteKit({
      title: 'Run Progress Lab',
      description: 'Measure how your running fitness changed over the years, then plan what comes next, from your own Garmin data.',
      repo: 'https://github.com/DavideBisio/garmin-run-progress',
      // Same mark and tab icon as the hub (copied from davidebisio.github.io/public).
      logo: '/logo.jpg',
      favicon: '/favicon.png',
      nav: [
        { label: 'Overview', href: '/' },
        { label: 'Docs', href: '/docs/' },
        // The single-file app from tools/build.py, copied into public/app/ by `npm run app:copy`.
        { label: 'App', href: '/app/' },
      ],
      // Opt-in, off by default: analytics: { goatcounter: 'davidebisio' },
    }),
  ],
});
