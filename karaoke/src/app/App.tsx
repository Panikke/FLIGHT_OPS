import { useState, useEffect, useCallback } from 'react';
import { SongLibrary } from './components/SongLibrary';
import { KaraokePlayer } from './components/KaraokePlayer';
import { BulkUploadDialog } from './components/BulkUploadDialog';
import { BulkImageDialog } from './components/BulkImageDialog';
import { EditSongDialog } from './components/EditSongDialog';
import { Music, FolderUp, Images } from 'lucide-react';
import type { LyricLine } from '../utils/lrcParser';
import { dbSave, dbLoadAll, dbDelete, dbDeleteAll, dbUpdate } from '../utils/storage';
import { searchLyrics } from '../utils/lyricsApi';

export interface Song {
  id: string;
  title: string;
  artist: string;
  audioUrl: string;
  lyrics: string;
  syncedLyrics: LyricLine[];
  lyricsSource: 'manual' | 'api' | 'file' | 'none';
  language: string;
  lyricsImageUrl?: string;
  coverArtUrl?: string;
}

export interface SongUploadPayload {
  title: string;
  artist: string;
  language: string;
  lyrics: string;
  syncedLyrics: LyricLine[];
  lyricsSource: Song['lyricsSource'];
  audioFile: File;
  lyricsImageFile?: File;
}

export default function App() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [currentSong, setCurrentSong] = useState<Song | null>(null);
  const [playlistIds, setPlaylistIds] = useState<Set<string>>(new Set());
  const [showBulkUpload, setShowBulkUpload] = useState(false);
  const [showBulkImages, setShowBulkImages] = useState(false);
  const [editingSong, setEditingSong] = useState<Song | null>(null);
  const [loading, setLoading] = useState(true);

  // Load persisted songs from IndexedDB on mount
  useEffect(() => {
    dbLoadAll().then(stored => {
      const loaded: Song[] = stored.map(s => ({
        id: s.id,
        title: s.title,
        artist: s.artist,
        language: s.language,
        lyrics: s.lyrics,
        syncedLyrics: s.syncedLyrics,
        lyricsSource: s.lyricsSource,
        audioUrl: URL.createObjectURL(s.audioBlob),
        lyricsImageUrl: s.lyricsImageBlob ? URL.createObjectURL(s.lyricsImageBlob) : undefined,
        coverArtUrl: s.coverArtBlob ? URL.createObjectURL(s.coverArtBlob) : undefined,
      }));
      setSongs(loaded);
      setPlaylistIds(new Set(loaded.map(s => s.id)));
    }).finally(() => setLoading(false));
  }, []);

  const addSongs = useCallback(async (payloads: SongUploadPayload[]) => {
    const newSongs: Song[] = [];
    for (const p of payloads) {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const audioUrl = URL.createObjectURL(p.audioFile);
      const lyricsImageUrl = p.lyricsImageFile ? URL.createObjectURL(p.lyricsImageFile) : undefined;
      await dbSave({
        id, title: p.title, artist: p.artist, language: p.language,
        lyrics: p.lyrics, syncedLyrics: p.syncedLyrics, lyricsSource: p.lyricsSource,
        audioBlob: p.audioFile, lyricsImageBlob: p.lyricsImageFile,
      });
      newSongs.push({ id, title: p.title, artist: p.artist, language: p.language,
        lyrics: p.lyrics, syncedLyrics: p.syncedLyrics, lyricsSource: p.lyricsSource,
        audioUrl, lyricsImageUrl });
    }
    setSongs(prev => [...prev, ...newSongs]);
    setPlaylistIds(prev => {
      const next = new Set(prev);
      newSongs.forEach(s => next.add(s.id));
      return next;
    });
  }, []);

  const deleteSong = useCallback(async (id: string) => {
    await dbDelete(id);
    setSongs(prev => {
      const song = prev.find(s => s.id === id);
      if (song) {
        URL.revokeObjectURL(song.audioUrl);
        if (song.lyricsImageUrl) URL.revokeObjectURL(song.lyricsImageUrl);
        if (song.coverArtUrl) URL.revokeObjectURL(song.coverArtUrl);
      }
      return prev.filter(s => s.id !== id);
    });
    setPlaylistIds(prev => { const n = new Set(prev); n.delete(id); return n; });
    if (currentSong?.id === id) setCurrentSong(null);
  }, [currentSong]);

  const clearLibrary = useCallback(async () => {
    await dbDeleteAll();
    setSongs(prev => {
      prev.forEach(s => {
        URL.revokeObjectURL(s.audioUrl);
        if (s.lyricsImageUrl) URL.revokeObjectURL(s.lyricsImageUrl);
        if (s.coverArtUrl) URL.revokeObjectURL(s.coverArtUrl);
      });
      return [];
    });
    setPlaylistIds(new Set());
    setCurrentSong(null);
  }, []);

  const updateCoverArt = useCallback(async (songId: string, imageFile: File) => {
    const coverArtUrl = URL.createObjectURL(imageFile);
    await dbUpdate(songId, { coverArtBlob: imageFile });
    setSongs(prev => prev.map(s => {
      if (s.id !== songId) return s;
      if (s.coverArtUrl) URL.revokeObjectURL(s.coverArtUrl);
      return { ...s, coverArtUrl };
    }));
    setCurrentSong(prev => prev?.id === songId ? { ...prev, coverArtUrl } : prev);
  }, []);

  const updateLyrics = useCallback(async (songId: string, lyrics: string, syncedLyrics: LyricLine[], source: Song['lyricsSource']) => {
    await dbUpdate(songId, { lyrics, syncedLyrics, lyricsSource: source });
    setSongs(prev => prev.map(s => s.id === songId ? { ...s, lyrics, syncedLyrics, lyricsSource: source } : s));
    setCurrentSong(prev => prev?.id === songId ? { ...prev, lyrics, syncedLyrics, lyricsSource: source } : prev);
  }, []);

  const updateLyricsImage = useCallback(async (songId: string, imageFile: File) => {
    const lyricsImageUrl = URL.createObjectURL(imageFile);
    await dbUpdate(songId, { lyricsImageBlob: imageFile });
    setSongs(prev => prev.map(s => {
      if (s.id !== songId) return s;
      if (s.lyricsImageUrl) URL.revokeObjectURL(s.lyricsImageUrl);
      return { ...s, lyricsImageUrl };
    }));
    setCurrentSong(prev => prev?.id === songId ? { ...prev, lyricsImageUrl } : prev);
  }, []);

  const updateSong = useCallback(async (id: string, patch: { title: string; artist: string; language: string }) => {
    await dbUpdate(id, patch);
    setSongs(prev => prev.map(s => s.id === id ? { ...s, ...patch } : s));
    setCurrentSong(prev => prev?.id === id ? { ...prev, ...patch } : prev);
  }, []);

  const togglePlaylist = useCallback((id: string) => {
    setPlaylistIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  // Bulk lyrics search — called from SongLibrary with an array of song IDs
  const bulkSearchLyrics = useCallback(async (ids: string[]) => {
    for (const id of ids) {
      const song = songs.find(s => s.id === id);
      if (!song) continue;
      try {
        const result = await searchLyrics(song.title, song.artist);
        if (result) await updateLyrics(id, result.plain, result.synced, 'api');
      } catch { /* continue */ }
    }
  }, [songs, updateLyrics]);

  const playlist = songs.filter(s => playlistIds.has(s.id));

  if (loading) {
    return (
      <div className="size-full bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center">
        <div className="text-white text-2xl">Loading library…</div>
      </div>
    );
  }

  return (
    <div className="size-full bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 text-white">
      {currentSong ? (
        <KaraokePlayer
          song={currentSong}
          playlist={playlist}
          onSelectSong={setCurrentSong}
          onBack={() => setCurrentSong(null)}
          onUpdateLyrics={updateLyrics}
        />
      ) : (
        <div className="size-full flex flex-col">
          <header className="bg-black/30 backdrop-blur-sm border-b border-white/10 px-6 py-4 flex-shrink-0">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <Music className="w-8 h-8 text-pink-400 flex-shrink-0" />
                <h1 className="text-2xl font-bold tracking-tight truncate">Karaoke</h1>
                <span className="text-sm text-gray-400 flex-shrink-0">{songs.length} songs</span>
                {playlistIds.size < songs.length && (
                  <span className="text-xs text-yellow-400 flex-shrink-0">{playlistIds.size} in playlist</span>
                )}
              </div>
              <div className="flex gap-3 flex-shrink-0">
                <button
                  onClick={() => setShowBulkImages(true)}
                  className="px-5 py-3 min-h-[48px] bg-gradient-to-r from-emerald-500 to-teal-500 rounded-xl hover:from-emerald-600 hover:to-teal-600 transition-all flex items-center gap-2 font-medium"
                >
                  <Images className="w-5 h-5" />
                  <span className="hidden sm:inline">Bulk Add Images</span>
                </button>
                <button
                  onClick={() => setShowBulkUpload(true)}
                  className="px-5 py-3 min-h-[48px] bg-gradient-to-r from-blue-500 to-cyan-500 rounded-xl hover:from-blue-600 hover:to-cyan-600 transition-all flex items-center gap-2 font-medium"
                >
                  <FolderUp className="w-5 h-5" />
                  <span className="hidden sm:inline">Bulk Upload Songs</span>
                </button>
              </div>
            </div>
          </header>

          <SongLibrary
            songs={songs}
            playlistIds={playlistIds}
            onSelectSong={setCurrentSong}
            onDeleteSong={deleteSong}
            onEditSong={setEditingSong}
            onTogglePlaylist={togglePlaylist}
            onSearchLyrics={bulkSearchLyrics}
            onClearLibrary={clearLibrary}
            onUpdateLyrics={updateLyrics}
            onAssignLyricsImage={updateLyricsImage}
          />
        </div>
      )}

      {showBulkUpload && (
        <BulkUploadDialog onClose={() => setShowBulkUpload(false)} onUpload={addSongs} />
      )}
      {showBulkImages && (
        <BulkImageDialog songs={songs} onClose={() => setShowBulkImages(false)} onApply={updateCoverArt} />
      )}
      {editingSong && (
        <EditSongDialog song={editingSong} onClose={() => setEditingSong(null)} onSave={updateSong} />
      )}
    </div>
  );
}
