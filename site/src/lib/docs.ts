import { getCollection, type CollectionEntry } from 'astro:content';

// The Markdown is the repo's own docs/, read on GitHub too, so sidebar metadata lives here
// instead of in frontmatter. Groups appear in this order: Overview, Features, Roadmap.
// A README.md is published at <dir>/readme/ (the kit's .md link rewriting expects that);
// docs/roadmap/ itself redirects to the roadmap README (astro.config.mjs).
const OVERVIEW = ['readme', 'architecture', 'runs-json-format', 'plan-json-format', 'deploy'];

// Same order as the tables in docs/README.md: the grabber, the analysis page, then the planner.
const FEATURES = [
  'incremental-grabber',
  'gpx-to-stream',
  'resting-heart-rate',
  'grabber-download',
  'data-loading-and-storage',
  'grade-adjusted-pace',
  'pace-at-heart-rate',
  'best-efforts-and-vdot',
  'yearly-trends',
  'aerobic-decoupling',
  'form-and-training-effect',
  'training-load-zones-consistency',
  'plan-profile',
  'plan-workouts',
  'plan-push',
];

type Doc = CollectionEntry<'docs'>;

function rank(list: string[], name: string): number {
  const i = list.indexOf(name);
  return i === -1 ? list.length : i;
}

function decorate(entry: Doc): Doc {
  const [dir, name] = entry.id.includes('/') ? entry.id.split('/', 2) : ['', entry.id];
  let meta: { group: string; order: number; title?: string };
  if (dir === 'features') {
    meta = { group: 'Features', order: 100 + rank(FEATURES, name) };
  } else if (dir === 'roadmap') {
    // README first, then the sections 00-10 by their number
    const nn = /^(\d+)-/.exec(name);
    meta = name === 'readme'
      ? { group: 'Roadmap', order: 200, title: 'Roadmap' }
      : { group: 'Roadmap', order: 201 + (nn ? Number(nn[1]) : 99) };
  } else {
    meta = { group: 'Overview', order: rank(OVERVIEW, name), ...(name === 'readme' ? { title: 'Overview' } : {}) };
  }
  return { ...entry, data: { ...entry.data, ...meta, title: entry.data.title ?? meta.title } };
}

/** Docs entries with sidebar group and order (and a title for the two READMEs) filled in. */
export async function getDocs(): Promise<Doc[]> {
  return (await getCollection('docs', (e) => !e.data.draft)).map(decorate);
}
