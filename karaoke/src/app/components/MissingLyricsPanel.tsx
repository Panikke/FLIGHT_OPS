import { useRef, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCw, Pencil, Image, Loader2, CheckCircle } from 'lucide-react';
import type { Song } from '../App';
import type { LyricLine } from '../../utils/lrcParser';

interface MissingLyricsPanelProps {
  songs: Song[];                    // only songs with no text lyrics
  onSearchOnline: (id: string) => Promise<void>;
  onManualEdit: (song: Song) => void;
  onAssignImage: (songId: string, file: File) => Promise<void>;
}

export function MissingLyricsPanel({ songs, onSearchOnline, onManualEdit, onAssignImage }: MissingLyricsPanelProps) {
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<Set<string>>(new Set());
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});

  if (songs.length === 0) return null;

  const handleSearch = async (id: string) => {
    setSearching(prev => new Set(prev).add(id));
    await onSearchOnline(id);
    setSearching(prev => { const n = new Set(prev); n.delete(id); return n; });
    setDone(prev => new Set(prev).add(id));
  };

  const handleFile = async (songId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await onAssignImage(songId, file);
    setDone(prev => new Set(prev).add(songId));
    e.target.value = '';
  };

  return (
    <div className="flex-shrink-0 border-t border-white/10 bg-black/20">
      {/* Header toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-sm font-semibold text-yellow-300">Missing Lyrics</span>
          <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded-full">{songs.length}</span>
          <span className="text-xs text-gray-500 hidden sm:inline">— click to search, add manually, or assign an image</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />}
      </button>

      {/* Song list */}
      {open && (
        <div className="overflow-y-auto max-h-64 px-3 pb-3" style={{ scrollbarWidth: 'thin' }}>
          <div className="space-y-1">
            {songs.map(song => {
              const isSearching = searching.has(song.id);
              const isDone = done.has(song.id);
              return (
                <div key={song.id} className="flex items-center gap-3 bg-black/20 hover:bg-black/30 rounded-xl px-3 py-2 transition-colors">
                  {/* Thumbnail */}
                  {song.coverArtUrl
                    ? <img src={song.coverArtUrl} alt="" className="w-10 h-10 rounded-lg object-cover flex-shrink-0" />
                    : <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0 text-base">🎵</div>
                  }

                  {/* Title / artist */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{song.title}</p>
                    <p className="text-xs text-gray-400 truncate">{song.artist}</p>
                  </div>

                  {/* Status / actions */}
                  {isDone ? (
                    <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                  ) : (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {/* Search online */}
                      <button
                        onClick={() => handleSearch(song.id)}
                        disabled={isSearching}
                        title="Search for lyrics online"
                        className="flex items-center gap-1 px-2.5 py-1.5 bg-purple-600/80 hover:bg-purple-600 disabled:bg-gray-700 rounded-lg text-xs transition-colors"
                      >
                        {isSearching
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <RefreshCw className="w-3.5 h-3.5" />
                        }
                        <span className="hidden sm:inline">{isSearching ? 'Searching…' : 'Search'}</span>
                      </button>

                      {/* Manual entry */}
                      <button
                        onClick={() => onManualEdit(song)}
                        title="Add lyrics manually"
                        className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg text-xs transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Manual</span>
                      </button>

                      {/* Assign image */}
                      <button
                        onClick={() => fileRefs.current[song.id]?.click()}
                        title="Use a lyrics image"
                        className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-600/80 hover:bg-emerald-600 rounded-lg text-xs transition-colors"
                      >
                        <Image className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Image</span>
                      </button>
                      <input
                        ref={el => { fileRefs.current[song.id] = el; }}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={e => handleFile(song.id, e)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
