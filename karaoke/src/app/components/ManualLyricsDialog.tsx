import { useState } from 'react';
import { X, Save, FileText } from 'lucide-react';
import type { Song } from '../App';
import { parseLrc } from '../../utils/lrcParser';
import type { LyricLine } from '../../utils/lrcParser';

interface ManualLyricsDialogProps {
  song: Song;
  onClose: () => void;
  onSave: (id: string, lyrics: string, synced: LyricLine[], source: Song['lyricsSource']) => Promise<void>;
}

function detectLrc(text: string): boolean {
  return /\[\d{1,2}:\d{2}[.:]\d{1,3}\]/.test(text);
}

export function ManualLyricsDialog({ song, onClose, onSave }: ManualLyricsDialogProps) {
  const existingLyrics = song.syncedLyrics.length > 0
    ? song.syncedLyrics.map(l => `[${Math.floor(l.time / 60).toString().padStart(2, '0')}:${(l.time % 60).toFixed(2).padStart(5, '0')}] ${l.text}`).join('\n')
    : song.lyrics;
  const [text, setText] = useState(existingLyrics);
  const [saving, setSaving] = useState(false);

  const isLrc = detectLrc(text);

  const handleSave = async () => {
    setSaving(true);
    const trimmed = text.trim();
    if (isLrc) {
      const synced = parseLrc(trimmed);
      const plain = trimmed.replace(/\[\d+:\d+[.:]\d+\]\s*/g, '');
      await onSave(song.id, plain, synced, 'manual');
    } else {
      await onSave(song.id, trimmed, [], 'manual');
    }
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-white/20 rounded-2xl w-full max-w-2xl flex flex-col max-h-[90vh]">

        <div className="flex items-center justify-between px-6 py-5 border-b border-white/10 flex-shrink-0">
          <div>
            <h2 className="text-xl font-bold">Add Lyrics Manually</h2>
            <p className="text-sm text-gray-400 mt-0.5">{song.title} — {song.artist}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 flex-1 overflow-hidden flex flex-col gap-3 min-h-0">
          <div className="flex items-center gap-3 text-sm">
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${isLrc ? 'bg-pink-500/20 text-pink-300' : 'bg-green-500/20 text-green-300'}`}>
              <FileText className="w-3.5 h-3.5" />
              {isLrc ? 'LRC format detected — synced lyrics' : 'Plain text — unsynced lyrics'}
            </div>
            <p className="text-gray-500 text-xs">Paste plain text or LRC time-coded format. LRC is auto-detected.</p>
          </div>

          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={`Paste lyrics here…\n\nFor time-synced LRC format:\n[00:12.50] First line of song\n[00:16.20] Second line`}
            className="flex-1 min-h-0 w-full px-4 py-3 bg-black/40 border border-white/20 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 resize-none font-mono text-sm leading-relaxed"
            style={{ scrollbarWidth: 'thin' }}
          />
        </div>

        <div className="flex gap-3 px-6 py-4 border-t border-white/10 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !text.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 disabled:from-gray-600 disabled:to-gray-600 rounded-xl transition-all font-medium"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save Lyrics'}
          </button>
        </div>
      </div>
    </div>
  );
}
