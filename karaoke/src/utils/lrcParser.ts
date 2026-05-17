export interface LyricLine {
  time: number; // seconds
  text: string;
}

const LINE_RE = /\[(\d{1,2}):(\d{2})\.(\d{1,3})\](.*)/;

export function parseLrc(lrc: string): LyricLine[] {
  const lines: LyricLine[] = [];
  for (const raw of lrc.split('\n')) {
    const m = raw.match(LINE_RE);
    if (!m) continue;
    const minutes = parseInt(m[1], 10);
    const seconds = parseInt(m[2], 10);
    // centiseconds or milliseconds depending on digit count
    const frac = m[3].length === 3 ? parseInt(m[3], 10) / 1000 : parseInt(m[3], 10) / 100;
    const text = m[4].trim();
    if (text) lines.push({ time: minutes * 60 + seconds + frac, text });
  }
  return lines.sort((a, b) => a.time - b.time);
}

export function getCurrentLineIndex(lines: LyricLine[], currentTime: number): number {
  if (lines.length === 0) return -1;
  let idx = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].time <= currentTime) idx = i;
    else break;
  }
  return idx;
}
