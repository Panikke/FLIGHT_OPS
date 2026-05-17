import { useState, useRef } from 'react';
import { X, Upload, Music, FileText, Image as ImageIcon } from 'lucide-react';
import type { Song } from '../App';

interface UploadDialogProps {
  onClose: () => void;
  onUpload: (song: Omit<Song, 'id'>) => void;
}

export function UploadDialog({ onClose, onUpload }: UploadDialogProps) {
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [language, setLanguage] = useState('English');
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [lyricsImageFile, setLyricsImageFile] = useState<File | null>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const lyricsImageInputRef = useRef<HTMLInputElement>(null);

  const handleAudioChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAudioFile(file);
    }
  };

  const handleLyricsImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setLyricsImageFile(file);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!title || !artist || !audioFile) {
      alert('Please fill in title, artist, and audio file');
      return;
    }

    if (!lyrics && !lyricsImageFile) {
      alert('Please provide lyrics (text or image)');
      return;
    }

    const audioUrl = URL.createObjectURL(audioFile);
    const lyricsImageUrl = lyricsImageFile ? URL.createObjectURL(lyricsImageFile) : undefined;

    onUpload({
      title,
      artist,
      audioUrl,
      lyrics,
      language,
      lyricsImageUrl,
    });

    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-white/20 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-gray-900/95 backdrop-blur-sm border-b border-white/10 p-6 flex items-center justify-between">
          <h2 className="text-2xl">Upload New Song</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div>
            <label className="block mb-2 text-sm text-gray-300">Song Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-3 bg-black/30 border border-white/20 rounded-lg text-white focus:outline-none focus:border-purple-500"
              placeholder="Enter song title"
            />
          </div>

          <div>
            <label className="block mb-2 text-sm text-gray-300">Artist *</label>
            <input
              type="text"
              value={artist}
              onChange={(e) => setArtist(e.target.value)}
              className="w-full px-4 py-3 bg-black/30 border border-white/20 rounded-lg text-white focus:outline-none focus:border-purple-500"
              placeholder="Enter artist name"
            />
          </div>

          <div>
            <label className="block mb-2 text-sm text-gray-300">Language *</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full px-4 py-3 bg-black/30 border border-white/20 rounded-lg text-white focus:outline-none focus:border-purple-500"
            >
              <option value="English">English</option>
              <option value="Greek">Greek (Ελληνικά)</option>
              <option value="Spanish">Spanish</option>
              <option value="French">French</option>
              <option value="German">German</option>
              <option value="Italian">Italian</option>
              <option value="Portuguese">Portuguese</option>
              <option value="Japanese">Japanese</option>
              <option value="Korean">Korean</option>
              <option value="Mandarin">Mandarin</option>
            </select>
          </div>

          <div>
            <label className="block mb-2 text-sm text-gray-300">Audio File *</label>
            <input
              ref={audioInputRef}
              type="file"
              accept="audio/*"
              onChange={handleAudioChange}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => audioInputRef.current?.click()}
              className="w-full flex items-center justify-center gap-3 px-4 py-6 bg-black/30 border-2 border-dashed border-white/20 rounded-lg hover:border-purple-500 transition-colors"
            >
              {audioFile ? (
                <>
                  <Music className="w-6 h-6 text-green-400" />
                  <span className="text-green-400">{audioFile.name}</span>
                </>
              ) : (
                <>
                  <Upload className="w-6 h-6 text-gray-400" />
                  <span className="text-gray-400">Click to upload audio file</span>
                </>
              )}
            </button>
            <p className="mt-2 text-xs text-gray-500">Supports MP3, WAV, OGG, M4A, and other audio formats</p>
          </div>

          <div>
            <label className="block mb-2 text-sm text-gray-300 flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Lyrics *
            </label>

            <div className="mb-3">
              <input
                ref={lyricsImageInputRef}
                type="file"
                accept="image/*"
                onChange={handleLyricsImageChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => lyricsImageInputRef.current?.click()}
                className="w-full flex items-center justify-center gap-3 px-4 py-4 bg-black/30 border border-white/20 rounded-lg hover:border-purple-500 transition-colors"
              >
                {lyricsImageFile ? (
                  <>
                    <ImageIcon className="w-5 h-5 text-green-400" />
                    <span className="text-green-400">{lyricsImageFile.name}</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-5 h-5 text-gray-400" />
                    <span className="text-gray-400">Upload lyrics image (optional)</span>
                  </>
                )}
              </button>
              <p className="mt-1 text-xs text-gray-500">Upload an image with lyrics to display during playback</p>
            </div>

            <textarea
              value={lyrics}
              onChange={(e) => setLyrics(e.target.value)}
              className="w-full px-4 py-3 bg-black/30 border border-white/20 rounded-lg text-white focus:outline-none focus:border-purple-500 min-h-[200px] font-mono"
              placeholder="Or enter lyrics here as text... (one line per verse)"
            />
            <p className="mt-2 text-xs text-gray-500">Provide either an image or text lyrics</p>
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-6 py-3 bg-gradient-to-r from-pink-500 to-purple-500 rounded-lg hover:from-pink-600 hover:to-purple-600 transition-all"
            >
              Upload Song
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
