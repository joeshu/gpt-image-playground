import type { StoredImage, TaskParams, TaskRecord } from '../types'
import { putImage, putTask } from './db'

const ROOT = (import.meta.env.VITE_COMPAT_API_ROOT || '').replace(/\/$/, '')
const TOKEN = import.meta.env.VITE_COMPAT_API_TOKEN || ''
const authHeaders = () => TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}
const DEFAULT_PARAMS: TaskParams = { size: 'auto', quality: 'auto', output_format: 'png', output_compression: null, moderation: 'auto', n: 1, transparent_output: false }

type ServerImage = { image_id?: string; task_id?: string; path?: string; thumbnail_path?: string; created_at?: string; favorite?: number; metadata_json?: string }

function url(path: string) { return `${ROOT}${path}` }
function imageUrl(path: string) { return url(`/v1/files?path=${encodeURIComponent(path)}`) }
function parseMeta(raw?: string): Record<string, unknown> { try { const x = raw ? JSON.parse(raw) : {}; return x && typeof x === 'object' ? x : {} } catch { return {} } }

async function fetchDataUrl(path: string): Promise<string> {
  const response = await fetch(imageUrl(path), { headers: authHeaders() })
  if (!response.ok) throw new Error(`画廊图片加载失败（HTTP ${response.status}）`)
  const blob = await response.blob()
  return await new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob)
  })
}

export async function syncCompatGallery(limit = 200): Promise<TaskRecord[]> {
  const response = await fetch(url(`/v1/gallery?limit=${limit}`), { headers: { Accept: 'application/json', ...authHeaders() } })
  if (!response.ok) throw new Error(`画廊同步失败（HTTP ${response.status}）`)
  const body = await response.json() as { items?: ServerImage[] }
  const tasks: TaskRecord[] = []
  for (const item of body.items ?? []) {
    if (!item.image_id || !item.path) continue
    const meta = parseMeta(item.metadata_json)
    const dataUrl = await fetchDataUrl(item.path)
    const stored: StoredImage = { id: item.image_id, dataUrl, createdAt: Date.parse(item.created_at || '') || Date.now(), source: 'generated' }
    await putImage(stored)
    const createdAt = stored.createdAt || Date.now()
    tasks.push({
      id: item.task_id || `server-image-${item.image_id}`,
      prompt: typeof meta.prompt === 'string' ? meta.prompt : '',
      params: { ...DEFAULT_PARAMS, ...(meta.params && typeof meta.params === 'object' ? meta.params as Partial<TaskParams> : {}) },
      apiProvider: typeof meta.provider === 'string' ? meta.provider : 'openai',
      apiProfileId: typeof meta.profile === 'string' ? meta.profile : undefined,
      apiModel: typeof meta.model === 'string' ? meta.model : undefined,
      inputImageIds: [], outputImages: [item.image_id], status: 'done', error: null,
      createdAt, finishedAt: createdAt, elapsed: null,
      isFavorite: Boolean(item.favorite), favoriteCollectionIds: Boolean(item.favorite) ? ['all-favorites'] : [],
      sourceMode: 'gallery',
      rawImageUrls: [imageUrl(item.path)],
      rawResponsePayload: JSON.stringify({ source: 'compat-gallery', image: item }),
    })
  }
  for (const task of tasks) await putTask(task)
  return tasks
}

export async function setCompatFavorite(imageId: string, favorite: boolean) {
  const response = await fetch(url('/v1/favorite'), { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ image_id: imageId, favorite }) })
  if (!response.ok) throw new Error('收藏状态同步失败')
}

export async function deleteCompatImages(imageIds: string[], removeFiles = false) {
  const response = await fetch(url('/v1/delete-images'), { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ image_ids: imageIds, remove_files: removeFiles }) })
  if (!response.ok) throw new Error('图片删除同步失败')
}
