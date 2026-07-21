/**
 * Client-side fuzzy email search over emails Odysseus has already listed/cached.
 * Avoids brittle IMAP SEARCH (TEXT/OR) while the inbox list is loaded locally.
 */

import Fuse from '../../lib/fuse.mjs';

const DEFAULT_FUSE_OPTIONS = {
  keys: [
    { name: 'from_name', weight: 0.35 },
    { name: 'from_address', weight: 0.25 },
    { name: 'subject', weight: 0.30 },
    { name: 'cached_summary', weight: 0.10 },
    { name: '_searchText', weight: 0.05 },
  ],
  threshold: 0.4,
  ignoreLocation: true,
  minMatchCharLength: 2,
  includeScore: true,
};

/**
 * Stable dedupe key for an email row in the search corpus.
 * Prefer message_id when present; fall back to uid+folder.
 */
export function emailSearchKey(em, folderFallback = '') {
  const mid = String(em?.message_id || '').trim();
  if (mid) return `mid:${mid}`;
  const uid = String(em?.uid || '').trim();
  const folder = String(em?._folder || folderFallback || '').trim();
  return `uid:${folder}:${uid}`;
}

/**
 * Build a searchable text blob from list-row fields.
 */
export function emailSearchBlob(em) {
  return [
    em?.subject,
    em?.from_name,
    em?.from_address,
    em?.to,
    em?.cc,
    em?.cached_summary,
    ...(Array.isArray(em?.tags) ? em.tags : []),
  ].filter(Boolean).join(' ');
}

/**
 * Merge current grid rows + optional list-cache entries into one corpus.
 *
 * @param {object} opts
 * @param {Array} opts.emails - Current `state._libEmails` slice
 * @param {Map|Iterable} [opts.listCache] - `_libListCache` Map entries
 * @param {string} [opts.accountId] - When set, only include cache rows for this account
 * @param {string} [opts.folderFallback] - Folder tag for rows without `_folder`
 */
export function buildEmailSearchCorpus({
  emails = [],
  listCache = null,
  accountId = '',
  folderFallback = '',
} = {}) {
  const seen = new Map();

  const add = (em, folderTag) => {
    if (!em || em.uid == null || em.uid === '') return;
    const row = em._folder ? em : { ...em, _folder: folderTag || folderFallback || '' };
    const key = emailSearchKey(row, folderTag || folderFallback || '');
    if (!seen.has(key)) seen.set(key, row);
  };

  for (const em of emails) add(em, em._folder || folderFallback);

  if (listCache && typeof listCache.forEach === 'function') {
    listCache.forEach((entry, cacheKey) => {
      if (accountId) {
        const keyAccount = String(cacheKey).split('|')[0] || '';
        if (keyAccount && keyAccount !== accountId) return;
      }
      const folderFromKey = String(cacheKey).split('|')[1] || '';
      for (const em of entry?.emails || []) {
        add(em, em._folder || folderFromKey);
      }
    });
  }

  return [...seen.values()].map((em) => ({
    ...em,
    _searchText: emailSearchBlob(em),
  }));
}

/**
 * Fuzzy-search a prebuilt corpus. Returns items sorted by relevance then date.
 */
export function searchEmailCorpus(query, corpus, { limit = 100, fuseOptions = {} } = {}) {
  const q = String(query || '').trim();
  if (q.length < 2) return [];
  if (!Array.isArray(corpus) || corpus.length === 0) return [];

  const fuse = new Fuse(corpus, { ...DEFAULT_FUSE_OPTIONS, ...fuseOptions });
  const hits = fuse.search(q, { limit: Math.max(1, limit) }).map((r) => r.item);

  hits.sort((a, b) => {
    const da = a.date_epoch || (a.date ? Date.parse(a.date) : 0) || 0;
    const db = b.date_epoch || (b.date ? Date.parse(b.date) : 0) || 0;
    return db - da;
  });
  return hits;
}

/**
 * Convenience: build corpus + search in one call.
 */
export function searchEmailsLocal(query, opts = {}) {
  const corpus = buildEmailSearchCorpus(opts);
  return searchEmailCorpus(query, corpus, opts);
}
