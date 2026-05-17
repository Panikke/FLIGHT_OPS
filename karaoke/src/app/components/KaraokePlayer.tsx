import { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowLeft, Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import type { Song } from '../App';
import { getCurrentLineIndex } from '../../utils/lrcParser';
import { searchLyrics } from '../../utils/lyricsApi';

interface KaraokePlayerProps {
  song: Song;
  playlist: Song[];
  onBack: () => void;
  onSelectSong: (song: Song) => void;
  onUpdateLyrics: (id: string, lyrics: string, synced: import('../../utils/lrcParser').LyricLine[], source: Song['lyricsSource']) => Promise<void>;
}

export function KaraokePlayer({ song, playlist, onBack, onSelectSong, onUpdateLyrics }: KaraokePlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [searchingLyrics, setSearchingLyrics] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const lyricsContainerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<(HTMLParagraphElement | null)[]>([]);

  const hasSynced = song.syncedLyrics.length > 0;
  const hasPlain = song.lyrics.trim().length > 0;

  const plainLines = hasPlain ? song.lyrics.split('\n').filter(l => l.trim()) : [];
  const syncedLines = song.syncedLyrics;

  const currentSyncedIdx = hasSynced ? getCurrentLineIndex(syncedLines, currentTime) : -1;
  const currentPlainIdx = (!hasSynced && hasPlain && duration > 0)
    ? Math.min(Math.floor((currentTime / duration) * plainLines.length), plainLines.length - 1)
    : -1;
  const currentLineIdx = hasSynced ? currentSyncedIdx : currentPlainIdx;

  // Auto-scroll active line into view
  useEffect(() => {
    if (currentLineIdx >= 0) {
      lineRefs.current[currentLineIdx]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [currentLineIdx]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => setCurrentTime(audio.currentTime);
    const onMeta = () => setDuration(audio.duration);
    const onEnd = () => setIsPlaying(false);
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('ended', onEnd);
    return () => {
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('ended', onEnd);
    };
  }, [song.audioUrl]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = muted ? 0 : volume;
  }, [volume, muted]);

  // Reset state when song changes
  useEffect(() => {
    setIsPlaying(false);
    setCurrentTime(0);
  }, [song.id]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) audio.pause(); else audio.play();
    setIsPlaying(!isPlaying);
  };

  const seek = (v: number) => {
    if (audioRef.current) { audioRef.current.currentTime = v; setCurrentTime(v); }
  };

  const skip = (s: number) => {
    if (audioRef.current) audioRef.current.currentTime = Math.max(0, Math.min(duration, currentTime + s));
  };

  const fmt = (t: number) => {
    if (!isFinite(t)) return '0:00';
    return `${Math.floor(t / 60)}:${Math.floor(t % 60).toString().padStart(2, '0')}`;
  };

  const currentIdx = playlist.findIndex(s => s.id === song.id);
  const prevSong = currentIdx > 0 ? playlist[currentIdx - 1] : null;
  const nextSong = currentIdx < playlist.length - 1 ? playlist[currentIdx + 1] : null;

  const handleSearchLyrics = useCallback(async () => {
    setSearchingLyrics(true);
    try {
      const result = await searchLyrics(song.title, song.artist);
      if (result) {
        await onUpdateLyrics(song.id, result.plain, result.synced, 'api');
      }
    } finally {
      setSearchingLyrics(false);
    }
  }, [song.id, song.title, song.artist, onUpdateLyrics]);

  const lyricsLines = hasSynced ? syncedLines.map(l => l.text) : plainLines;
  const hasLyrics = lyricsLines.length > 0;

  return (
    <div className="size-full flex flex-col">
      <audio ref={audioRef} src={song.audioUrl} />

      <header className="bg-black/30 backdrop-blur-sm border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
          <span>Library</span>
        </button>
        <div className="flex items-center gap-2">
          {prevSong && (
            <button onClick={() => onSelectSong(prevSong)} className="flex items-center gap-1 px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded-lg text-sm transition-colors">
              <ChevronLeft className="w-4 h-4" /> Prev
            </button>
          )}
          {nextSong && (
            <button onClick={() => onSelectSong(nextSong)} className="flex items-center gap-1 px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded-lg text-sm transition-colors">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 flex flex-col items-center justify-between px-8 py-6 overflow-hidden">
        {/* Song info + cover art */}
        <div className="flex items-center gap-6 mb-4 w-full max-w-4xl">
          {song.coverArtUrl ? (
            <img src={song.coverArtUrl} alt="Cover art" className="w-20 h-20 rounded-xl object-cover shadow-lg flex-shrink-0" />
          ) : (
            <div className="w-20 h-20 rounded-xl bg-white/10 flex items-center justify-center flex-shrink-0">
              <span className="text-3xl">🎵</span>
            </div>
          )}
          <div>
            <h1 className="text-3xl font-bold">{song.title}</h1>
            <p className="text-xl text-gray-300 mt-1">{song.artist}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-2 py-0.5 bg-white/10 rounded-full text-gray-400">{song.language}</span>
              {hasSynced && <span className="text-xs px-2 py-0.5 bg-pink-500/30 text-pink-300 rounded-full">Synced lyrics</span>}
              {!hasLyrics && <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-300 rounded-full">No lyrics</span>}
            </div>
          </div>
          {!hasLyrics && (
            <button
              onClick={handleSearchLyrics}
              disabled={searchingLyrics}
              className="ml-auto flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-lg text-sm transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${searchingLyrics ? 'animate-spin' : ''}`} />
              {searchingLyrics ? 'Searching...' : 'Find Lyrics'}
            </button>
          )}
        </div>

        {/* Lyrics display */}
        <div className="flex-1 w-full max-w-4xl bg-black/40 backdrop-blur-md border border-white/20 rounded-2xl overflow-hidden mb-6 min-h-0">
          {song.lyricsImageUrl ? (
            <div className="h-full overflow-y-auto flex items-center justify-center p-4">
              <img src={song.lyricsImageUrl} alt="Lyrics" className="max-w-full max-h-full object-contain rounded" />
            </div>
          ) : hasLyrics ? (
            <div ref={lyricsContainerRef} className="h-full overflow-y-auto py-8 px-6 flex flex-col gap-3 items-center">
              {lyricsLines.map((line, i) => {
                const isActive = i === currentLineIdx;
                const isPast = i < currentLineIdx;
                const isNext = i === currentLineIdx + 1;
                return (
                  <p
                    key={i}
                    ref={el => { lineRefs.current[i] = el; }}
                    className={`text-center transition-all duration-300 select-none ${
                      isActive
                        ? 'text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-pink-400 to-purple-400 scale-105'
                        : isPast
                        ? 'text-lg text-gray-600'
                        : isNext
                        ? 'text-2xl text-gray-300'
                        : 'text-xl text-gray-500'
                    }`}
                  >
                    {line}
                  </p>
                );
              })}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center gap-4">
              <p className="text-gray-400 text-lg">No lyrics available</p>
              <button
                onClick={handleSearchLyrics}
                disabled={searchingLyrics}
                className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-lg transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${searchingLyrics ? 'animate-spin' : ''}`} />
                {searchingLyrics ? 'Searching online...' : 'Search for Lyrics'}
              </button>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="w-full max-w-4xl">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs text-gray-400 w-10 text-right tabular-nums">{fmt(currentTime)}</span>
            <input
              type="range" min={0} max={duration || 0} value={currentTime}
              onChange={e => seek(Number(e.target.value))}
              className="flex-1 h-1.5 bg-white/20 rounded-full appearance-none cursor-pointer accent-pink-500"
            />
            <span className="text-xs text-gray-400 w-10 tabular-nums">{fmt(duration)}</span>
          </div>

          <div className="flex items-center justify-center gap-6 mb-4">
            <button onClick={() => skip(-10)} className="p-3 hover:bg-white/10 rounded-full transition-colors">
              <SkipBack className="w-6 h-6" />
            </button>
            <button
              onClick={togglePlay}
              className="p-5 bg-gradient-to-r from-pink-500 to-purple-500 rounded-full hover:from-pink-600 hover:to-purple-600 transition-all shadow-lg"
            >
              {isPlaying ? <Pause className="w-8 h-8" /> : <Play className="w-8 h-8 ml-0.5" />}
            </button>
            <button onClick={() => skip(10)} className="p-3 hover:bg-white/10 rounded-full transition-colors">
              <SkipForward className="w-6 h-6" />
            </button>
          </div>

          <div className="flex items-center justify-center gap-3">
            <button onClick={() => setMuted(m => !m)} className="text-gray-400 hover:text-white transition-colors">
              {muted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
            <input
              type="range" min={0} max={1} step={0.01} value={muted ? 0 : volume}
              onChange={e => { setVolume(Number(e.target.value)); setMuted(false); }}
              className="w-28 h-1.5 bg-white/20 rounded-full appearance-none cursor-pointer accent-white"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
