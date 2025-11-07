/**
 * IndexedDB utilities for persisting file uploads in the browser.
 * Stores the latest uploaded file and its metadata for recovery across sessions.
 */

const DB_NAME = "NordicPrivacyAI";
const DB_VERSION = 1;
const STORE_NAME = "latestUpload";

interface UploadedFileMeta {
  name: string;
  size: number;
  type: string;
  contentPreview: string;
}

interface LatestUploadData {
  file: File;
  meta: UploadedFileMeta;
  timestamp: number;
}

/**
 * Open or create the IndexedDB database
 */
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      
      // Create object store if it doesn't exist
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
  });
}

/**
 * Save the latest uploaded file and its metadata to IndexedDB
 */
export async function saveLatestUpload(
  file: File,
  meta: UploadedFileMeta
): Promise<void> {
  const db = await openDB();
  
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    
    const data: LatestUploadData = {
      file,
      meta,
      timestamp: Date.now(),
    };
    
    const request = store.put(data, "latest");
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
    
    transaction.oncomplete = () => db.close();
  });
}

/**
 * Retrieve the latest uploaded file and metadata from IndexedDB
 */
export async function getLatestUpload(): Promise<LatestUploadData> {
  const db = await openDB();
  
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get("latest");
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const result = request.result as LatestUploadData | undefined;
      if (result) {
        resolve(result);
      } else {
        reject(new Error("No cached upload found"));
      }
    };
    
    transaction.oncomplete = () => db.close();
  });
}

/**
 * Delete the latest upload from IndexedDB
 */
export async function deleteLatestUpload(): Promise<void> {
  const db = await openDB();
  
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete("latest");
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
    
    transaction.oncomplete = () => db.close();
  });
}
