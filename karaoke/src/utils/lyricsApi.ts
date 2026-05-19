import { parseLrc, type LyricLine } from './lrcParser';

interface LrclibResult {
  trackName: string;
  artistName: string;
  plainLyrics: string | null;
  syncedLyrics: string | null;
  instrumental: boolean;
}

export interface LyricsResult {
  plain: string;
  synced: LyricLine[];
  source: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function normalize(s: string) {
  return s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim();
}

/** Strip leading track numbers: "01_", "1 - ", "02. ", "3 ", etc. */
function stripTrackNumber(s: string): string {
  return s.replace(/^\d+[\s_\-\.]+/, '').trim();
}

/** Transliterate Greek characters to Latin equivalents for search fallback */
function greekToLatin(s: string): string {
  const map: Record<string, string> = {
    'α':'a','ά':'a','β':'v','γ':'g','δ':'d','ε':'e','έ':'e','ζ':'z',
    'η':'i','ή':'i','θ':'th','ι':'i','ί':'i','ϊ':'i','ΐ':'i','κ':'k',
    'λ':'l','μ':'m','ν':'n','ξ':'x','ο':'o','ό':'o','π':'p','ρ':'r',
    'σ':'s','ς':'s','τ':'t','υ':'y','ύ':'y','ϋ':'y','ΰ':'y','φ':'f',
    'χ':'ch','ψ':'ps','ω':'o','ώ':'o',
    'Α':'A','Ά':'A','Β':'V','Γ':'G','Δ':'D','Ε':'E','Έ':'E','Ζ':'Z',
    'Η':'I','Ή':'I','Θ':'Th','Ι':'I','Ί':'I','Ϊ':'I','Κ':'K','Λ':'L',
    'Μ':'M','Ν':'N','Ξ':'X','Ο':'O','Ό':'O','Π':'P','Ρ':'R','Σ':'S',
    'Τ':'T','Υ':'Y','Ύ':'Y','Ϋ':'Y','Φ':'F','Χ':'Ch','Ψ':'Ps','Ω':'O','Ώ':'O',
  };
  return s.split('').map(c => map[c] ?? c).join('');
}

function hasGreek(s: string): boolean {
  return /[Ͱ-Ͽἀ-῿]/.test(s);
}

function scoreMatch(result: LrclibResult, title: string, artist: string): number {
  const nt = normalize(result.trackName);
  const na = normalize(result.artistName);
  const qt = normalize(title);
  const qa = normalize(artist);
  let score = 0;
  if (nt === qt) score += 4;
  else if (nt.includes(qt) || qt.includes(nt)) score += 2;
  if (na === qa) score += 3;
  else if (na.includes(qa) || qa.includes(na)) score += 1;
  return score;
}

function pickBest(results: LrclibResult[], title: string, artist: string): LyricsResult | null {
  const scored = results
    .filter(r => !r.instrumental && (r.plainLyrics || r.syncedLyrics))
    .map(r => ({ r, score: scoreMatch(r, title, artist) }))
    .sort((a, b) => b.score - a.score);
  if (scored.length === 0) return null;
  const best = scored[0].r;
  const plain = best.plainLyrics ?? best.syncedLyrics?.replace(/\[\d+:\d+\.\d+\]\s*/g, '') ?? '';
  const synced = best.syncedLyrics ? parseLrc(best.syncedLyrics) : [];
  return { plain, synced, source: 'lrclib' };
}

// ── Source 1: lrclib.net ───────────────────────────────────────────────────
async function searchLrclib(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    const attempts: Array<[string, string]> = [
      [title, artist],                           // 1. original
    ];
    // Strip track numbers if present
    const cleanT = stripTrackNumber(title);
    const cleanA = stripTrackNumber(artist);
    if (cleanT !== title || cleanA !== artist) attempts.push([cleanT, cleanA]);

    // Greek → Latin transliteration fallbacks
    if (hasGreek(title) || hasGreek(artist)) {
      attempts.push([greekToLatin(cleanT), greekToLatin(cleanA)]);
      attempts.push([greekToLatin(cleanT), cleanA]);   // transliterate title only
      attempts.push([cleanT, greekToLatin(cleanA)]);   // transliterate artist only
    }

    for (const [t, a] of attempts) {
      // Try specific artist+track endpoint first
      const r1 = await fetch(`https://lrclib.net/api/search?${new URLSearchParams({ artist_name: a, track_name: t })}`);
      let results: LrclibResult[] = r1.ok ? await r1.json() : [];

      // Fall back to general query
      if (results.length === 0) {
        const r2 = await fetch(`https://lrclib.net/api/search?${new URLSearchParams({ q: `${t} ${a}` })}`);
        results = r2.ok ? await r2.json() : [];
      }

      // Title-only search (Greek artists stored differently)
      if (results.length === 0) {
        const r3 = await fetch(`https://lrclib.net/api/search?${new URLSearchParams({ q: t })}`);
        results = r3.ok ? await r3.json() : [];
      }

      const best = pickBest(results, t, a);
      if (best) return best;
    }
    return null;
  } catch {
    return null;
  }
}

// ── Source 2: lyrics.ovh ──────────────────────────────────────────────────
async function searchLyricsOvh(title: string, artist: string): Promise<LyricsResult | null> {
  const attempts: Array<[string, string]> = [[title, artist]];

  const cleanT = stripTrackNumber(title);
  const cleanA = stripTrackNumber(artist);
  if (cleanT !== title || cleanA !== artist) attempts.push([cleanT, cleanA]);

  // lyrics.ovh works best with Latin names — try transliteration for Greek
  if (hasGreek(title) || hasGreek(artist)) {
    attempts.push([greekToLatin(cleanT), greekToLatin(cleanA)]);
  }

  // Also try swapped (some Greek catalogues list artist/title reversed)
  attempts.push([cleanA, cleanT]);

  for (const [t, a] of attempts) {
    try {
      const url = `https://api.lyrics.ovh/v1/${encodeURIComponent(a)}/${encodeURIComponent(t)}`;
      const r = await fetch(url);
      if (!r.ok) continue;
      const data = await r.json() as { lyrics?: string; error?: string };
      if (data.lyrics && !data.error) {
        const plain = data.lyrics.trim();
        if (plain) return { plain, synced: [], source: 'lyrics.ovh' };
      }
    } catch {
      // continue to next attempt
    }
  }
  return null;
}

// ── Source 3: lrclib artist-catalog scan ──────────────────────────────────
// Fetches all songs by the artist on lrclib and picks the closest title match.
// Helps when the stored title has minor differences from the lrclib entry.
async function searchLrclibByScan(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    const cleanA = stripTrackNumber(artist);
    const latinA = hasGreek(cleanA) ? greekToLatin(cleanA) : cleanA;
    for (const a of [cleanA, latinA]) {
      const r = await fetch(`https://lrclib.net/api/search?${new URLSearchParams({ artist_name: a })}`);
      const results: LrclibResult[] = r.ok ? await r.json() : [];
      if (results.length > 0) {
        const best = pickBest(results, title, artist);
        if (best) return best;
      }
    }
    return null;
  } catch { return null; }
}

// ── Source 4: keyword search on lrclib ────────────────────────────────────
// Tries the first 3-4 words of the title as a keyword fallback.
async function searchLrclibKeywords(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    const clean = stripTrackNumber(hasGreek(title) ? greekToLatin(title) : title);
    const words = clean.split(/\s+/).slice(0, 4).join(' ');
    if (words.length < 3) return null;
    const r = await fetch(`https://lrclib.net/api/search?${new URLSearchParams({ q: words })}`);
    const results: LrclibResult[] = r.ok ? await r.json() : [];
    return pickBest(results, title, artist);
  } catch { return null; }
}

// ── Public API ─────────────────────────────────────────────────────────────
export async function searchLyrics(title: string, artist: string): Promise<LyricsResult | null> {
  // Stage 1: run primary sources in parallel (fast path)
  const [lrclib, ovh] = await Promise.all([
    searchLrclib(title, artist),
    searchLyricsOvh(title, artist),
  ]);

  // Prefer lrclib synced lyrics (time-coded karaoke)
  if (lrclib?.synced.length) return lrclib;
  // lyrics.ovh often has better Greek plain-lyrics coverage
  if (ovh) return ovh;
  // lrclib plain lyrics
  if (lrclib) return lrclib;

  // Stage 2: deeper fallbacks (slower — only reached when Stage 1 fails)
  const [scan, kw] = await Promise.all([
    searchLrclibByScan(title, artist),
    searchLrclibKeywords(title, artist),
  ]);

  if (scan?.synced.length) return scan;
  if (kw?.synced.length) return kw;
  if (scan) return scan;
  if (kw) return kw;

  return null;
}
