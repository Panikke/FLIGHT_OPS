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

export async function searchLyrics(title: string, artist: string): Promise<LyricsResult | null> {
  try {
    // Try artist + track search first
    const byTrack = new URLSearchParams({ artist_name: artist, track_name: title });
    const r1 = await fetch(`https://lrclib.net/api/search?${byTrack}`);
    let results: LrclibResult[] = r1.ok ? await r1.json() : [];

    // Fall back to general query if no results
    if (results.length === 0) {
      const byQ = new URLSearchParams({ q: `${title} ${artist}` });
      const r2 = await fetch(`https://lrclib.net/api/search?${byQ}`);
      results = r2.ok ? await r2.json() : [];
    }

    if (results.length === 0) return null;

    // Pick best scoring non-instrumental result
    const scored = results
      .filter(r => !r.instrumental && (r.plainLyrics || r.syncedLyrics))
      .map(r => ({ r, score: scoreMatch(r, title, artist) }))
      .sort((a, b) => b.score - a.score);

    if (scored.length === 0) return null;
    const best = scored[0].r;

    const plain = best.plainLyrics ?? best.syncedLyrics?.replace(/\[\d+:\d+\.\d+\]\s*/g, '') ?? '';
    const synced = best.syncedLyrics ? parseLrc(best.syncedLyrics) : [];

    return { plain, synced };
  } catch {
    return null;
  }
}
