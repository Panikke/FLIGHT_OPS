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

function normalize(s: string) {
  return s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim();
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

// ── Source 1: lrclib.net — best for synced lyrics ──────────────────────────
async function searchLrclib(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    const byTrack = new URLSearchParams({ artist_name: artist, track_name: title });
    const r1 = await fetch(`https://lrclib.net/api/search?${byTrack}`);
    let results: LrclibResult[] = r1.ok ? await r1.json() : [];

    if (results.length === 0) {
      const byQ = new URLSearchParams({ q: `${title} ${artist}` });
      const r2 = await fetch(`https://lrclib.net/api/search?${byQ}`);
      results = r2.ok ? await r2.json() : [];
    }

    // Also try title-only search for Greek songs where artist transliteration differs
    if (results.length === 0) {
      const byTitle = new URLSearchParams({ q: title });
      const r3 = await fetch(`https://lrclib.net/api/search?${byTitle}`);
      results = r3.ok ? await r3.json() : [];
    }

    if (results.length === 0) return null;

    const scored = results
      .filter(r => !r.instrumental && (r.plainLyrics || r.syncedLyrics))
      .map(r => ({ r, score: scoreMatch(r, title, artist) }))
      .sort((a, b) => b.score - a.score);

    if (scored.length === 0) return null;
    const best = scored[0].r;

    const plain = best.plainLyrics ?? best.syncedLyrics?.replace(/\[\d+:\d+\.\d+\]\s*/g, '') ?? '';
    const synced = best.syncedLyrics ? parseLrc(best.syncedLyrics) : [];
    return { plain, synced, source: 'lrclib' };
  } catch {
    return null;
  }
}

// ── Source 2: lyrics.ovh — better Greek & Southern European coverage ───────
async function searchLyricsOvh(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    const url = `https://api.lyrics.ovh/v1/${encodeURIComponent(artist)}/${encodeURIComponent(title)}`;
    const r = await fetch(url);
    if (!r.ok) return null;
    const data = await r.json() as { lyrics?: string; error?: string };
    if (!data.lyrics || data.error) return null;
    const plain = data.lyrics.trim();
    if (!plain) return null;
    return { plain, synced: [], source: 'lyrics.ovh' };
  } catch {
    return null;
  }
}

// ── Source 3: lyrics.ovh with swapped artist/title ─────────────────────────
// Greek songs are sometimes catalogued with title as artist or vice-versa
async function searchLyricsOvhSwapped(title: string, artist: string): Promise<LyricsResult | null> {
  return searchLyricsOvh(artist, title);
}

// ── Public API ─────────────────────────────────────────────────────────────
export async function searchLyrics(title: string, artist: string): Promise<LyricsResult | null> {
  // Run lrclib and lyrics.ovh in parallel for speed
  const [lrclib, ovh] = await Promise.all([
    searchLrclib(title, artist),
    searchLyricsOvh(title, artist),
  ]);

  // Prefer lrclib when it has synced lyrics
  if (lrclib?.synced.length) return lrclib;
  // Prefer lrclib plain if lyrics.ovh has nothing
  if (lrclib && !ovh) return lrclib;
  // Prefer lyrics.ovh if lrclib had nothing
  if (ovh && !lrclib) return ovh;
  // Both found — prefer synced, otherwise lrclib (generally higher quality)
  if (lrclib) return lrclib;

  // Last resort: try swapped artist/title on lyrics.ovh (helps some Greek entries)
  return searchLyricsOvhSwapped(title, artist);
}
