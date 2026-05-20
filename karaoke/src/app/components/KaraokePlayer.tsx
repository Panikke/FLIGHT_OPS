import { useState, useRef, useEffect, useCallback } from 'react';
import {
  ArrowLeft, Play, Pause, SkipBack, SkipForward,
  Volume2, VolumeX, Maximize, Minimize, RefreshCw,
  ChevronLeft, ChevronRight, ListMusic, X,
} from 'lucide-react';
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
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [searchingLyrics, setSearchingLyrics] = useState(false);
  const [showImageLyrics, setShowImageLyrics] = useState(false);
  const [queue, setQueue] = useState<Song[]>([]);

  const audioRef = useRef<HTMLAudioElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const lyricsContainerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<(HTMLParagraphElement | null)[]>([]);
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queueRef = useRef<Song[]>([]);
  const playlistRef = useRef<Song[]>([]);
  const currentSongRef = useRef<Song>(song);

  // Keep refs in sync for use inside event listeners
  useEffect(() => { queueRef.current = queue; }, [queue]);
  useEffect(() => { playlistRef.current = playlist; }, [playlist]);
  useEffect(() => { currentSongRef.current = song; }, [song]);

  const hasSynced = song.syncedLyrics.length > 0;
  const hasPlain = song.lyrics.trim().length > 0;
  const plainLines = hasPlain ? song.lyrics.split('\n').filter(l => l.trim()) : [];
  const syncedLines = song.syncedLyrics;
  const currentSyncedIdx = hasSynced ? getCurrentLineIndex(syncedLines, currentTime) : -1;
  const currentPlainIdx = (!hasSynced && hasPlain && duration > 0)
    ? Math.min(Math.floor((currentTime / duration) * plainLines.length), plainLines.length - 1)
    : -1;
  const currentLineIdx = hasSynced ? currentSyncedIdx : currentPlainIdx;
  const lyricsLines = hasSynced ? syncedLines.map(l => l.text) : plainLines;
  const hasLyrics = lyricsLines.length > 0;

  const currentIdx = playlist.findIndex(s => s.id === song.id);
  const sequentialNext = currentIdx < playlist.length - 1 ? playlist[currentIdx + 1] : null;
  const prevSong = currentIdx > 0 ? playlist[currentIdx - 1] : null;
  // Effective next: queue first, then sequential
  const nextSong = queue.length > 0 ? queue[0] : sequentialNext;

  // "Up Next" panel: queue items + sequential remaining (deduplicated, capped at 20)
  const upNext: Array<{ song: Song; queued: boolean }> = [
    ...queue.map(s => ({ song: s, queued: true })),
    ...playlist
      .slice(currentIdx + 1)
      .filter(s => !queue.some(q => q.id === s.id))
      .map(s => ({ song: s, queued: false })),
  ].slice(0, 20);

  // "All Songs" panel: everything except current song
  const otherSongs = playlist.filter(s => s.id !== song.id);

  const addToQueue = useCallback((s: Song) => {
    setQueue(prev => [s, ...prev.filter(q => q.id !== s.id)]);
  }, []);

  const removeFromQueue = useCallback((id: string) => {
    setQueue(prev => prev.filter(q => q.id !== id));
  }, []);

  const goNext = useCallback(() => {
    const q = queueRef.current;
    if (q.length > 0) {
      const next = q[0];
      setQueue(prev => prev.slice(1));
      onSelectSong(next);
    } else {
      const pl = playlistRef.current;
      const idx = pl.findIndex(s => s.id === currentSongRef.current.id);
      if (idx < pl.length - 1) onSelectSong(pl[idx + 1]);
    }
  }, [onSelectSong]);

  // Auto-scroll active lyric line
  useEffect(() => {
    if (currentLineIdx >= 0) {
      lineRefs.current[currentLineIdx]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [currentLineIdx]);

  // Audio events
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => setCurrentTime(audio.currentTime);
    const onMeta = () => setDuration(audio.duration);
    const onEnd = () => { setIsPlaying(false); goNext(); };
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('ended', onEnd);
    return () => {
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('ended', onEnd);
    };
  }, [song.audioUrl, goNext]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = muted ? 0 : volume;
  }, [volume, muted]);

  // Reset on song change
  useEffect(() => {
    setIsPlaying(false);
    setCurrentTime(0);
    lineRefs.current = [];
    setShowImageLyrics(false);   // always reset to text-first on new song
  }, [song.id]);

  // Wake Lock
  useEffect(() => {
    if (isPlaying) {
      (navigator as Navigator & { wakeLock?: { request: (type: string) => Promise<WakeLockSentinel> } })
        .wakeLock?.request('screen')
        .then(lock => { wakeLockRef.current = lock; })
        .catch(() => {});
    } else {
      wakeLockRef.current?.release().catch(() => {});
      wakeLockRef.current = null;
    }
    return () => { wakeLockRef.current?.release().catch(() => {}); };
  }, [isPlaying]);

  // Fullscreen tracking
  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // Media Session API
  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: song.title,
      artist: song.artist,
      artwork: song.coverArtUrl ? [{ src: song.coverArtUrl, sizes: '512x512', type: 'image/png' }] : [],
    });
    navigator.mediaSession.setActionHandler('play', () => { audioRef.current?.play(); setIsPlaying(true); });
    navigator.mediaSession.setActionHandler('pause', () => { audioRef.current?.pause(); setIsPlaying(false); });
    navigator.mediaSession.setActionHandler('previoustrack', prevSong ? () => onSelectSong(prevSong) : null);
    navigator.mediaSession.setActionHandler('nexttrack', nextSong ? goNext : null);
  }, [song, prevSong, nextSong, goNext, onSelectSong]);

  // Auto-hide controls in fullscreen
  const showControls = useCallback(() => {
    setControlsVisible(true);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      if (document.fullscreenElement) setControlsVisible(false);
    }, 3000);
  }, []);

  useEffect(() => {
    if (!isFullscreen) {
      setControlsVisible(true);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    } else {
      showControls();
    }
    return () => { if (hideTimerRef.current) clearTimeout(hideTimerRef.current); };
  }, [isFullscreen, showControls]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) { audio.pause(); setIsPlaying(false); }
    else { audio.play(); setIsPlaying(true); }
  }, [isPlaying]);

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

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen();
    else document.exitFullscreen();
  };

  const handleSearchLyrics = useCallback(async () => {
    setSearchingLyrics(true);
    try {
      const result = await searchLyrics(song.title, song.artist);
      if (result) await onUpdateLyrics(song.id, result.plain, result.synced, 'api');
    } finally {
      setSearchingLyrics(false);
    }
  }, [song.id, song.title, song.artist, onUpdateLyrics]);

  const controlsFade = isFullscreen && !controlsVisible ? 'opacity-0 pointer-events-none' : 'opacity-100';

  return (
    <div
      ref={containerRef}
      className="size-full flex flex-col bg-gradient-to-br from-purple-950 via-blue-950 to-indigo-950 text-white select-none"
      onPointerMove={showControls}
      onPointerDown={showControls}
    >
      <audio ref={audioRef} src={song.audioUrl} />

      {/* ── Header ── */}
      <header className={`flex-shrink-0 bg-black/50 backdrop-blur-sm border-b border-white/10 px-3 py-2 flex items-center gap-2 transition-opacity duration-300 ${controlsFade}`}>
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-gray-300 hover:text-white min-w-[48px] min-h-[48px] px-3 rounded-lg hover:bg-white/10 transition-colors"
        >
          <ArrowLeft className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm hidden sm:inline">Library</span>
        </button>

        <div className="flex-1 text-center px-2 min-w-0">
          <p className="font-bold truncate leading-tight">{song.title}</p>
          <p className="text-sm text-gray-400 truncate leading-tight">{song.artist}</p>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          {prevSong && (
            <button onClick={() => onSelectSong(prevSong)} className="min-w-[48px] min-h-[48px] flex items-center justify-center hover:bg-white/10 rounded-lg transition-colors" title={prevSong.title}>
              <ChevronLeft className="w-5 h-5" />
            </button>
          )}
          {nextSong && (
            <button onClick={goNext} className="min-w-[48px] min-h-[48px] flex items-center justify-center hover:bg-white/10 rounded-lg transition-colors" title={nextSong.title}>
              <ChevronRight className="w-5 h-5" />
            </button>
          )}
          {!hasLyrics && (
            <button
              onClick={handleSearchLyrics}
              disabled={searchingLyrics}
              className="flex items-center gap-1.5 px-3 min-h-[48px] bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-lg text-sm transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${searchingLyrics ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{searchingLyrics ? 'Searching…' : 'Find Lyrics'}</span>
            </button>
          )}
          <button onClick={toggleFullscreen} className="min-w-[48px] min-h-[48px] flex items-center justify-center hover:bg-white/10 rounded-lg transition-colors">
            {isFullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
          </button>
        </div>
      </header>

      {/* ── Main three-column layout ── */}
      <div className="flex-1 flex overflow-hidden min-h-0">

        {/* ── Left panel — cover art + controls ── */}
        <div className={`flex-shrink-0 flex flex-col items-center justify-between py-4 px-5 w-[260px] lg:w-[300px] xl:w-[340px] border-r border-white/10 transition-opacity duration-300 ${controlsFade}`}>

          <div className="flex-1 flex items-center justify-center w-full min-h-0 py-2">
            {song.coverArtUrl ? (
              <img src={song.coverArtUrl} alt={song.title} className="rounded-2xl shadow-2xl object-cover max-h-full max-w-full aspect-square" />
            ) : (
              <div className="w-32 h-32 rounded-2xl bg-white/10 flex items-center justify-center shadow-xl">
                <span className="text-5xl">🎵</span>
              </div>
            )}
          </div>

          <div className="w-full space-y-1 mt-2">
            <input type="range" min={0} max={duration || 0} value={currentTime}
              onChange={e => seek(Number(e.target.value))}
              className="w-full h-2 bg-white/20 rounded-full appearance-none cursor-pointer accent-pink-500" />
            <div className="flex justify-between text-xs text-gray-400 tabular-nums px-0.5">
              <span>{fmt(currentTime)}</span>
              <span>{fmt(duration)}</span>
            </div>
          </div>

          <div className="flex items-center justify-center gap-3 mt-3">
            <button onClick={() => prevSong && onSelectSong(prevSong)} disabled={!prevSong}
              className="w-12 h-12 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors disabled:opacity-25">
              <SkipBack className="w-6 h-6" />
            </button>
            <button onClick={() => skip(-10)}
              className="w-11 h-11 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors text-xs font-bold text-gray-300">
              −10s
            </button>
            <button onClick={togglePlay}
              className="w-[72px] h-[72px] flex items-center justify-center bg-gradient-to-br from-pink-500 to-purple-600 rounded-full hover:from-pink-400 hover:to-purple-500 active:scale-95 transition-all shadow-lg shadow-purple-900/50">
              {isPlaying ? <Pause className="w-8 h-8" /> : <Play className="w-8 h-8 ml-1" />}
            </button>
            <button onClick={() => skip(10)}
              className="w-11 h-11 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors text-xs font-bold text-gray-300">
              +10s
            </button>
            <button onClick={goNext} disabled={!nextSong}
              className="w-12 h-12 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors disabled:opacity-25">
              <SkipForward className="w-6 h-6" />
            </button>
          </div>

          <div className="flex items-center gap-2 mt-3 w-full">
            <button onClick={() => setMuted(m => !m)}
              className="w-10 h-10 flex items-center justify-center text-gray-400 hover:text-white transition-colors flex-shrink-0">
              {muted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
            <input type="range" min={0} max={1} step={0.01} value={muted ? 0 : volume}
              onChange={e => { setVolume(Number(e.target.value)); setMuted(false); }}
              className="flex-1 h-2 bg-white/20 rounded-full appearance-none cursor-pointer accent-white" />
          </div>
        </div>

        {/* ── Centre panel — lyrics ── */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {/* Text/Image toggle — shown only when both exist */}
          {hasLyrics && song.lyricsImageUrl && (
            <div className="flex-shrink-0 flex justify-end px-4 pt-2">
              <button
                onClick={() => setShowImageLyrics(v => !v)}
                className="text-xs px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded-lg transition-colors text-gray-300"
              >
                {showImageLyrics ? '📝 Show text lyrics' : '🖼 Show image lyrics'}
              </button>
            </div>
          )}
          {/* Lyrics image — shown when: no text lyrics, OR user toggled to image */}
          {(showImageLyrics || !hasLyrics) && song.lyricsImageUrl ? (
            <div className="flex-1 overflow-y-auto flex items-center justify-center p-4">
              <img src={song.lyricsImageUrl} alt="Lyrics" className="max-w-full max-h-full object-contain rounded-xl" />
            </div>
          ) : hasLyrics ? (
            <div ref={lyricsContainerRef} className="flex-1 overflow-y-auto py-12 px-6 flex flex-col items-center gap-4"
              style={{ scrollbarWidth: 'none' }} onClick={togglePlay}>
              {lyricsLines.map((line, i) => {
                const isActive = i === currentLineIdx;
                const isPast = i < currentLineIdx;
                const isNext = i === currentLineIdx + 1;
                const isFar = i > currentLineIdx + 3 || i < currentLineIdx - 3;
                return (
                  <p key={i} ref={el => { lineRefs.current[i] = el; }}
                    className={`text-center leading-snug transition-all duration-300 ${
                      isActive ? 'text-4xl xl:text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-pink-400 via-fuchsia-300 to-cyan-400 scale-105'
                        : isPast ? 'text-lg text-gray-700'
                        : isNext ? 'text-2xl text-gray-300'
                        : isFar ? 'text-base text-gray-600'
                        : 'text-xl text-gray-500'
                    }`}>
                    {line || ' '}
                  </p>
                );
              })}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
              <span className="text-7xl opacity-20">🎤</span>
              <p className="text-gray-400 text-2xl">No lyrics available</p>
              <button onClick={handleSearchLyrics} disabled={searchingLyrics}
                className="flex items-center gap-2 px-8 py-4 min-h-[56px] bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-2xl text-lg transition-colors shadow-lg">
                <RefreshCw className={`w-5 h-5 ${searchingLyrics ? 'animate-spin' : ''}`} />
                {searchingLyrics ? 'Searching online…' : 'Search for Lyrics'}
              </button>
            </div>
          )}
        </div>

        {/* ── Right panel — Up Next + All Songs ── */}
        <div className="flex-shrink-0 w-[200px] lg:w-[220px] xl:w-[240px] border-l border-white/10 flex flex-col overflow-hidden">

          {/* Up Next */}
          <div className="flex-shrink-0 border-b border-white/10 flex flex-col" style={{ maxHeight: '45%' }}>
            <div className="flex items-center gap-2 px-3 py-2 flex-shrink-0">
              <ListMusic className="w-4 h-4 text-purple-400 flex-shrink-0" />
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Up Next</span>
              {queue.length > 0 && (
                <span className="ml-auto text-xs px-1.5 py-0.5 bg-pink-500/30 text-pink-300 rounded-full">{queue.length}</span>
              )}
            </div>
            <div className="overflow-y-auto flex-1" style={{ scrollbarWidth: 'none' }}>
              {upNext.length === 0 ? (
                <p className="text-xs text-gray-600 px-3 pb-3">No songs queued</p>
              ) : (
                upNext.map(({ song: s, queued }) => (
                  <div key={s.id}
                    className="flex items-center gap-2 px-3 py-2 hover:bg-white/5 cursor-pointer group"
                    onClick={() => onSelectSong(s)}>
                    {s.coverArtUrl
                      ? <img src={s.coverArtUrl} alt="" className="w-8 h-8 rounded object-cover flex-shrink-0" />
                      : <div className="w-8 h-8 rounded bg-white/10 flex items-center justify-center flex-shrink-0 text-xs">🎵</div>
                    }
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{s.title}</p>
                      <p className="text-xs text-gray-500 truncate">{s.artist}</p>
                    </div>
                    {queued ? (
                      <button onClick={e => { e.stopPropagation(); removeFromQueue(s.id); }}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-all flex-shrink-0">
                        <X className="w-3 h-3" />
                      </button>
                    ) : (
                      <div className="w-1.5 h-1.5 rounded-full bg-white/20 flex-shrink-0" />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* All Songs */}
          <div className="flex-1 flex flex-col overflow-hidden min-h-0">
            <div className="flex items-center gap-2 px-3 py-2 flex-shrink-0 border-b border-white/5">
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">All Songs</span>
              <span className="ml-auto text-xs text-gray-600">{otherSongs.length}</span>
            </div>
            <div className="overflow-y-auto flex-1" style={{ scrollbarWidth: 'none' }}>
              {otherSongs.map(s => {
                const isQueued = queue.some(q => q.id === s.id);
                return (
                  <div key={s.id}
                    className={`flex items-center gap-2 px-3 py-2 cursor-pointer group transition-colors ${isQueued ? 'bg-pink-500/10' : 'hover:bg-white/5'}`}
                    onClick={() => addToQueue(s)}>
                    {s.coverArtUrl
                      ? <img src={s.coverArtUrl} alt="" className="w-8 h-8 rounded object-cover flex-shrink-0" />
                      : <div className="w-8 h-8 rounded bg-white/10 flex items-center justify-center flex-shrink-0 text-xs">🎵</div>
                    }
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{s.title}</p>
                      <p className="text-xs text-gray-500 truncate">{s.artist}</p>
                    </div>
                    {isQueued
                      ? <span className="text-xs text-pink-400 flex-shrink-0">✓</span>
                      : <span className="text-xs text-gray-600 opacity-0 group-hover:opacity-100 flex-shrink-0">+</span>
                    }
                  </div>
                );
              })}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
