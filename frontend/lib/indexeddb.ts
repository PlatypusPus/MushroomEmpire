/**
 * IndexedDB utilities for caching uploaded files
 */

const DB_NAME = 'ShroomShield';
const STORE_NAME = 'uploads';
const DB_VERSION = 1;

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
  });
}

export interface UploadedFileMeta {
  name: string;
  size: number;
  type: string;
  contentPreview: string;
}

export async function saveLatestUpload(file: File, meta: UploadedFileMeta): Promise<void> {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readwrite');
  const store = transaction.objectStore(STORE_NAME);
  
  await new Promise((resolve, reject) => {
    const request = store.put({ file, meta }, 'latest');
    request.onsuccess = () => resolve(undefined);
    request.onerror = () => reject(request.error);
  });
  
  db.close();
}

export async function getLatestUpload(): Promise<{ file: File; meta: UploadedFileMeta } | { file: null; meta: null }> {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readonly');
  const store = transaction.objectStore(STORE_NAME);
  
  const result = await new Promise<any>((resolve, reject) => {
    const request = store.get('latest');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  
  db.close();
  return result || { file: null, meta: null };
}

export async function deleteLatestUpload(): Promise<void> {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readwrite');
  const store = transaction.objectStore(STORE_NAME);
  
  await new Promise((resolve, reject) => {
    const request = store.delete('latest');
    request.onsuccess = () => resolve(undefined);
    request.onerror = () => reject(request.error);
  });
  
  db.close();
}
