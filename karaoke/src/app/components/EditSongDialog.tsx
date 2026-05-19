import { useState } from 'react';
import { X, Save } from 'lucide-react';
import type { Song } from '../App';

interface EditSongDialogProps {
  song: Song;
  onClose: () => void;
  onSave: (id: string, patch: { title: string; artist: string; language: string }) => Promise<void>;
}

const LANGUAGES = [
  'Greek (Ελληνικά)', 'English', 'Spanish', 'Italian', 'French',
  'Portuguese', 'German', 'Arabic', 'Turkish', 'Other',
];

export function EditSongDialog({ song, onClose, onSave }: EditSongDialogProps) {
  const [title, setTitle] = useState(song.title);
  const [artist, setArtist] = useState(song.artist);
  const [language, setLanguage] = useState(song.language);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(song.id, { title: title.trim(), artist: artist.trim(), language });
    setSaving(false);
    onClose();
  };

  const inputCls = 'w-full px-4 py-3 bg-black/30 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500';

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-white/20 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/10">
          <h2 className="text-xl font-bold">Edit Song</h2>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Title</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              className={inputCls}
              placeholder="Song title"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Artist</label>
            <input
              value={artist}
              onChange={e => setArtist(e.target.value)}
              className={inputCls}
              placeholder="Artist name"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Language</label>
            <select
              value={language}
              onChange={e => setLanguage(e.target.value)}
              className={`${inputCls} cursor-pointer`}
            >
              {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
              {!LANGUAGES.includes(language) && (
                <option value={language}>{language}</option>
              )}
            </select>
          </div>
        </div>

        <div className="flex gap-3 px-6 py-4 border-t border-white/10">
          <button onClick={onClose} className="flex-1 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !title.trim() || !artist.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 disabled:from-gray-600 disabled:to-gray-600 rounded-xl transition-all font-medium"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
