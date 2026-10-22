import { docsCollection } from '@davidebisio/site-kit/content';

// The docs are the repo's own Markdown, published where it lives so the site never drifts:
// docs/architecture.md becomes /docs/architecture/, docs/features/<name>.md becomes
// /docs/features/<name>/ and docs/roadmap/<nn-name>.md becomes /docs/roadmap/<nn-name>/.
// The files have no frontmatter: titles come from their "# heading", and sidebar groups
// and order are set in src/lib/docs.ts.
export const collections = {
  docs: docsCollection({ base: '../docs', pattern: ['**/*.md'] }),
};
