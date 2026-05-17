import type { LyricLine } from './lrcParser';

const DB_NAME = 'karaoke-db';
const DB_VERSION = 1;
const STORE = 'songs';

export interface StoredSong {
  id: string;
  title: string;
  artist: string;
  language: string;
  lyrics: string;
  syncedLyrics: LyricLine[];
  lyricsSource: 'manual' | 'api' | 'file' | 'none';
  audioBlob: Blob;
  lyricsImageBlob?: Blob;
  coverArtBlob?: Blob;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(db: IDBDatabase, mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const req = fn(t.objectStore(STORE));
    t.oncomplete = () => resolve(req.result);
    t.onerror = () => reject(t.error);
  });
}

export async function dbSave(song: StoredSong): Promise<void> {
  const db = await openDB();
  await tx(db, 'readwrite', s => s.put(song));
}

export async function dbLoadAll(): Promise<StoredSong[]> {
  const db = await openDB();
  return tx<StoredSong[]>(db, 'readonly', s => s.getAll());
}

export async function dbDelete(id: string): Promise<void> {
  const db = await openDB();
  await tx(db, 'readwrite', s => s.delete(id));
}

export async function dbUpdate(id: string, patch: Partial<Omit<StoredSong, 'id' | 'audioBlob'>>): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, 'readwrite');
    const store = t.objectStore(STORE);
    const req = store.get(id);
    req.onsuccess = () => {
      if (req.result) store.put({ ...req.result, ...patch });
    };
    t.oncomplete = () => resolve();
    t.onerror = () => reject(t.error);
  });
}
