import { useState } from 'react';
import { Search, Play, Trash2, Music2 } from 'lucide-react';
import type { Song } from '../App';

interface SongLibraryProps {
  songs: Song[];
  onSelectSong: (song: Song) => void;
  onDeleteSong: (id: string) => void;
}

const lyricsBadge = (song: Song) => {
  if (song.syncedLyrics.length > 0) return { label: 'Synced', cls: 'bg-pink-500/20 text-pink-300' };
  if (song.lyrics.trim()) return { label: 'Lyrics', cls: 'bg-green-500/20 text-green-300' };
  if (song.lyricsImageUrl) return { label: 'Image', cls: 'bg-blue-500/20 text-blue-300' };
  return { label: 'No lyrics', cls: 'bg-yellow-500/20 text-yellow-300' };
};

export function SongLibrary({ songs, onSelectSong, onDeleteSong }: SongLibraryProps) {
  const [query, setQuery] = useState('');

  const filtered = songs.filter(s => {
    const q = query.toLowerCase();
    return !q || s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q) || s.language.toLowerCase().includes(q);
  });

  return (
    <div className="flex-1 overflow-hidden flex flex-col p-6">
      <div className="mb-5 relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
        <input
          type="text"
          placeholder="Search by title, artist, or language…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="w-full pl-12 pr-4 py-3.5 bg-black/30 backdrop-blur-sm border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-gray-400">
            <Music2 className="w-16 h-16 opacity-20" />
            <p className="text-xl">{songs.length === 0 ? 'No songs yet — click Bulk Upload Songs to start' : 'No results'}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map(song => {
              const badge = lyricsBadge(song);
              return (
                <div
                  key={song.id}
                  className="bg-black/30 backdrop-blur-sm border border-white/10 rounded-xl hover:border-purple-500/60 transition-all group cursor-pointer"
                  onClick={() => onSelectSong(song)}
                >
                  {/* Cover art with play overlay */}
                  <div className="relative h-40 bg-gradient-to-br from-purple-900/40 to-blue-900/40 flex items-center justify-center rounded-t-xl overflow-hidden">
                    {song.coverArtUrl ? (
                      <img src={song.coverArtUrl} alt={song.title} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-5xl opacity-30">🎵</span>
                    )}

                    {/* Play overlay on hover */}
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <div className="w-14 h-14 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center border-2 border-white/60">
                        <Play className="w-6 h-6 text-white ml-0.5" />
                      </div>
                    </div>

                    {/* Lyrics badge */}
                    <span className={`absolute bottom-2 left-2 text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                      {badge.label}
                    </span>

                    {/* Delete button — stops propagation so it doesn't trigger play */}
                    <button
                      onClick={e => { e.stopPropagation(); onDeleteSong(song.id); }}
                      className="absolute top-2 right-2 p-1.5 bg-black/60 hover:bg-red-500/80 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-white" />
                    </button>
                  </div>

                  {/* Song info */}
                  <div className="p-4">
                    <h3 className="font-semibold truncate">{song.title}</h3>
                    <p className="text-sm text-gray-400 truncate mt-0.5">{song.artist}</p>
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
