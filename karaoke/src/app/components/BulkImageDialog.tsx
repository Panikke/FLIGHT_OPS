import { useState, useRef, useCallback } from 'react';
import { X, Images, CheckCircle, AlertCircle, Link2 } from 'lucide-react';
import type { Song } from '../App';

interface BulkImageDialogProps {
  songs: Song[];
  onClose: () => void;
  onApply: (songId: string, imageFile: File) => Promise<void>;
}

interface ImageMatch {
  file: File;
  previewUrl: string;
  matchedSongId: string | null;
  manualSongId: string | null;
}

function normalize(s: string) {
  return s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim();
}

function stripExt(name: string) {
  return name.replace(/\.[^/.]+$/, '');
}

function leadingNumber(name: string) {
  return name.match(/^(\d+)/)?.[1] ?? null;
}

function bestMatch(file: File, songs: Song[]): Song | null {
  const fileNorm = normalize(stripExt(file.name));
  const fileNum = leadingNumber(file.name);

  // 1. Leading number match
  if (fileNum) {
    for (const song of songs) {
      const songNum = leadingNumber(song.title) || leadingNumber(song.artist);
      if (songNum === fileNum) return song;
    }
  }

  // 2. Exact title match
  for (const song of songs) {
    if (normalize(song.title) === fileNorm) return song;
  }

  // 3. Substring match
  for (const song of songs) {
    const nt = normalize(song.title);
    const na = normalize(song.artist);
    if (fileNorm.includes(nt) || nt.includes(fileNorm)) return song;
    if (fileNorm.includes(na)) return song;
  }

  return null;
}

export function BulkImageDialog({ songs, onClose, onApply }: BulkImageDialogProps) {
  const [matches, setMatches] = useState<ImageMatch[]>([]);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []).filter(f =>
      /\.(jpg|jpeg|png|webp|gif|svg)$/i.test(f.name)
    );
    const newMatches: ImageMatch[] = files.map(file => ({
      file,
      previewUrl: URL.createObjectURL(file),
      matchedSongId: bestMatch(file, songs)?.id ?? null,
      manualSongId: null,
    }));
    setMatches(newMatches);
  }, [songs]);

  const setManual = (i: number, songId: string) => {
    setMatches(prev => prev.map((m, idx) => idx === i ? { ...m, manualSongId: songId || null } : m));
  };

  const effectiveSongId = (m: ImageMatch) => m.manualSongId ?? m.matchedSongId;

  const handleApply = async () => {
    setSaving(true);
    const toApply = matches.filter(m => effectiveSongId(m));
    for (const m of toApply) {
      await onApply(effectiveSongId(m)!, m.file);
    }
    setSaving(false);
    onClose();
  };

  const matchCount = matches.filter(m => effectiveSongId(m)).length;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-white/20 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">

        <div className="border-b border-white/10 px-6 py-5 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-2xl font-bold">Bulk Add Cover Images</h2>
            <p className="text-sm text-gray-400 mt-1">Upload JPEG / PNG files — automatically matched to songs by filename</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* File picker */}
          <input
            ref={inputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.gif,.svg,image/*"
            multiple
            onChange={handleFiles}
            className="hidden"
          />
          <button
            onClick={() => inputRef.current?.click()}
            className="w-full flex items-center justify-center gap-3 px-4 py-5 bg-black/30 border-2 border-dashed border-white/20 rounded-xl hover:border-emerald-400 transition-colors"
          >
            <Images className="w-6 h-6 text-emerald-400" />
            <span className="text-gray-300">
              {matches.length ? `${matches.length} images selected — click to change` : 'Select JPEG / PNG / WebP images'}
            </span>
          </button>

          {matches.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-400">
                {matchCount} of {matches.length} images matched to songs.
                {matchCount < matches.length && ' Use the dropdowns to assign unmatched ones manually.'}
              </p>

              {matches.map((m, i) => {
                const resolved = effectiveSongId(m);
                const song = songs.find(s => s.id === resolved);
                return (
                  <div key={i} className="flex items-center gap-4 bg-black/30 border border-white/10 rounded-xl p-3">
                    <img src={m.previewUrl} alt={m.file.name} className="w-14 h-14 object-cover rounded-lg flex-shrink-0" />

                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{m.file.name}</p>
                      {resolved ? (
                        <div className="flex items-center gap-1.5 mt-1">
                          <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                          <span className="text-xs text-green-400 truncate">→ {song?.title} – {song?.artist}</span>
                          {m.matchedSongId && !m.manualSongId && (
                            <span className="text-xs text-gray-500">(auto)</span>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 mt-1">
                          <AlertCircle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                          <span className="text-xs text-yellow-400">No match found</span>
                        </div>
                      )}
                    </div>

                    {/* Manual assignment */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Link2 className="w-4 h-4 text-gray-500" />
                      <select
                        value={m.manualSongId ?? m.matchedSongId ?? ''}
                        onChange={e => setManual(i, e.target.value)}
                        className="text-sm px-3 py-1.5 bg-black/40 border border-white/20 rounded-lg text-white focus:outline-none focus:border-purple-500 max-w-[200px]"
                      >
                        <option value="">— assign to song —</option>
                        {songs.map(s => (
                          <option key={s.id} value={s.id}>{s.title} – {s.artist}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {songs.length === 0 && (
            <p className="text-center text-gray-400 py-8">Upload some songs first before adding cover images.</p>
          )}
        </div>

        <div className="border-t border-white/10 px-6 py-4 flex gap-3 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={saving || matchCount === 0}
            className="flex-1 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 disabled:from-gray-600 disabled:to-gray-600 disabled:cursor-not-allowed rounded-lg transition-all font-medium"
          >
            {saving ? 'Saving...' : `Apply ${matchCount} Image${matchCount !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
    </div>
  );
}
