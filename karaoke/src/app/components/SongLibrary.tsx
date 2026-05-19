import { useState } from 'react';
import { Search, Play, Trash2, Music2, Pencil, ListMusic, ListX, CheckSquare, Square, RefreshCw, Loader2, AlertTriangle } from 'lucide-react';
import type { Song } from '../App';

interface SongLibraryProps {
  songs: Song[];
  playlistIds: Set<string>;
  onSelectSong: (song: Song) => void;
  onDeleteSong: (id: string) => void;
  onEditSong: (song: Song) => void;
  onTogglePlaylist: (id: string) => void;
  onSearchLyrics: (ids: string[]) => Promise<void>;
  onClearLibrary: () => void;
}

const lyricsBadge = (song: Song) => {
  if (song.syncedLyrics.length > 0) return { label: 'Synced', cls: 'bg-pink-500/20 text-pink-300' };
  if (song.lyrics.trim()) return { label: 'Lyrics', cls: 'bg-green-500/20 text-green-300' };
  if (song.lyricsImageUrl) return { label: 'Image', cls: 'bg-blue-500/20 text-blue-300' };
  return { label: 'No lyrics', cls: 'bg-yellow-500/20 text-yellow-300' };
};

export function SongLibrary({
  songs, playlistIds, onSelectSong, onDeleteSong, onEditSong,
  onTogglePlaylist, onSearchLyrics, onClearLibrary,
}: SongLibraryProps) {
  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchingLyrics, setSearchingLyrics] = useState(false);
  const [searchProgress, setSearchProgress] = useState<{ done: number; total: number } | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const filtered = songs.filter(s => {
    const q = query.toLowerCase();
    return !q || s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q) || s.language.toLowerCase().includes(q);
  });

  const allFilteredSelected = filtered.length > 0 && filtered.every(s => selectedIds.has(s.id));

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        filtered.forEach(s => next.delete(s.id));
        return next;
      });
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev);
        filtered.forEach(s => next.add(s.id));
        return next;
      });
    }
  };

  const handleBulkSearchLyrics = async () => {
    const ids = Array.from(selectedIds);
    setSearchingLyrics(true);
    setSearchProgress({ done: 0, total: ids.length });
    let done = 0;
    // Search in small batches to keep UI responsive
    for (const id of ids) {
      await onSearchLyrics([id]);
      done++;
      setSearchProgress({ done, total: ids.length });
    }
    setSearchingLyrics(false);
    setSearchProgress(null);
  };

  const handleClearLibrary = () => {
    setConfirmClear(false);
    onClearLibrary();
  };

  const selectedCount = Array.from(selectedIds).filter(id => filtered.some(s => s.id === id)).length;

  return (
    <div className="flex-1 overflow-hidden flex flex-col p-4 gap-3">

      {/* ── Search + bulk action bar ── */}
      <div className="flex gap-2 flex-wrap items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by title, artist, or language…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full pl-11 pr-4 py-3 bg-black/30 backdrop-blur-sm border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
          />
        </div>

        {/* Select All toggle */}
        <button
          onClick={toggleSelectAll}
          className="flex items-center gap-2 px-4 py-3 bg-black/30 border border-white/20 hover:border-purple-500/50 rounded-xl text-sm transition-colors"
        >
          {allFilteredSelected
            ? <CheckSquare className="w-4 h-4 text-purple-400" />
            : <Square className="w-4 h-4 text-gray-400" />
          }
          <span className="text-gray-300 hidden sm:inline">
            {allFilteredSelected ? 'Deselect All' : 'Select All'}
          </span>
        </button>

        {/* Bulk lyrics search */}
        {selectedCount > 0 && (
          <button
            onClick={handleBulkSearchLyrics}
            disabled={searchingLyrics}
            className="flex items-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 rounded-xl text-sm transition-colors"
          >
            {searchingLyrics
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <RefreshCw className="w-4 h-4" />
            }
            <span>
              {searchingLyrics && searchProgress
                ? `${searchProgress.done}/${searchProgress.total}`
                : `Search Lyrics (${selectedCount})`
              }
            </span>
          </button>
        )}

        {/* Clear library */}
        {songs.length > 0 && (
          confirmClear ? (
            <div className="flex items-center gap-2 px-4 py-3 bg-red-900/40 border border-red-500/50 rounded-xl text-sm">
              <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-red-300 hidden sm:inline">Delete all {songs.length} songs?</span>
              <button onClick={handleClearLibrary} className="px-2 py-0.5 bg-red-500 hover:bg-red-600 rounded text-white text-xs font-medium">Yes</button>
              <button onClick={() => setConfirmClear(false)} className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-white text-xs">No</button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmClear(true)}
              className="flex items-center gap-2 px-4 py-3 bg-black/30 border border-white/20 hover:border-red-500/50 hover:text-red-400 rounded-xl text-sm text-gray-400 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              <span className="hidden sm:inline">Clear Library</span>
            </button>
          )
        )}
      </div>

      {/* ── Song grid ── */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-gray-400">
            <Music2 className="w-16 h-16 opacity-20" />
            <p className="text-xl">{songs.length === 0 ? 'No songs yet — click Bulk Upload Songs to start' : 'No results'}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-4">
            {filtered.map(song => {
              const badge = lyricsBadge(song);
              const isSelected = selectedIds.has(song.id);
              const inPlaylist = playlistIds.has(song.id);
              return (
                <div
                  key={song.id}
                  className={`bg-black/30 backdrop-blur-sm border rounded-xl transition-all group cursor-pointer relative ${
                    isSelected
                      ? 'border-purple-500/80 ring-1 ring-purple-500/40'
                      : inPlaylist
                      ? 'border-white/10 hover:border-purple-500/60'
                      : 'border-white/5 opacity-60 hover:opacity-80 hover:border-white/20'
                  }`}
                  onClick={() => onSelectSong(song)}
                >
                  {/* Selection checkbox */}
                  <button
                    onClick={e => { e.stopPropagation(); toggleSelect(song.id); }}
                    className="absolute top-2 left-2 z-10 p-1"
                  >
                    {isSelected
                      ? <CheckSquare className="w-4 h-4 text-purple-400" />
                      : <Square className="w-4 h-4 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    }
                  </button>

                  {/* Cover art */}
                  <div className="relative h-40 bg-gradient-to-br from-purple-900/40 to-blue-900/40 flex items-center justify-center rounded-t-xl overflow-hidden">
                    {song.coverArtUrl
                      ? <img src={song.coverArtUrl} alt={song.title} className="w-full h-full object-cover" />
                      : <span className="text-5xl opacity-30">🎵</span>
                    }

                    {/* Play overlay */}
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <div className="w-14 h-14 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center border-2 border-white/60">
                        <Play className="w-6 h-6 text-white ml-0.5" />
                      </div>
                    </div>

                    {/* Lyrics badge */}
                    <span className={`absolute bottom-2 left-2 text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                      {badge.label}
                    </span>

                    {/* Playlist indicator */}
                    {!inPlaylist && (
                      <span className="absolute bottom-2 right-2 text-xs px-2 py-0.5 rounded-full bg-gray-700/80 text-gray-400">
                        Off playlist
                      </span>
                    )}

                    {/* Action buttons row */}
                    <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                      {/* Edit */}
                      <button
                        onClick={e => { e.stopPropagation(); onEditSong(song); }}
                        className="p-1.5 bg-black/60 hover:bg-blue-500/80 rounded-lg transition-colors"
                        title="Edit song info"
                      >
                        <Pencil className="w-3.5 h-3.5 text-white" />
                      </button>
                      {/* Playlist toggle */}
                      <button
                        onClick={e => { e.stopPropagation(); onTogglePlaylist(song.id); }}
                        className={`p-1.5 rounded-lg transition-colors ${inPlaylist ? 'bg-black/60 hover:bg-yellow-500/80' : 'bg-green-600/80 hover:bg-green-500'}`}
                        title={inPlaylist ? 'Remove from playlist' : 'Add to playlist'}
                      >
                        {inPlaylist
                          ? <ListX className="w-3.5 h-3.5 text-white" />
                          : <ListMusic className="w-3.5 h-3.5 text-white" />
                        }
                      </button>
                      {/* Delete */}
                      <button
                        onClick={e => { e.stopPropagation(); onDeleteSong(song.id); }}
                        className="p-1.5 bg-black/60 hover:bg-red-500/80 rounded-lg transition-colors"
                        title="Delete song"
                      >
                        <Trash2 className="w-3.5 h-3.5 text-white" />
                      </button>
                    </div>
                  </div>

                  {/* Song info */}
                  <div className="p-3">
                    <h3 className="font-semibold truncate text-sm">{song.title}</h3>
                    <p className="text-xs text-gray-400 truncate mt-0.5">{song.artist}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{song.language}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
