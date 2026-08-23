import { getActiveApiProfile } from './apiProfiles'
import type { CallApiOptions, CallApiResult } from './imageApiShared'

export type { CallApiOptions, CallApiResult } from './imageApiShared'
export { normalizeBaseUrl } from './devProxy'

/**
 * Current project adapter. The upstream UI remains unchanged; only its image
 * transport is redirected to this project's /v1/generate contract.
 */
const API_ROOT = (import.meta.env.VITE_COMPAT_API_ROOT || '').replace(/\/$/, '')

function apiUrl(path: string) { return `${API_ROOT}${path}` }
function headers() { return { 'Content-Type': 'application/json', Accept: 'application/json' } }

function outputValues(value: unknown, result: unknown[] = []): unknown[] {
  if (Array.isArray(value)) value.forEach(item => outputValues(item, result))
  else if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>
    if (typeof item.b64_json === 'string' || typeof item.base64 === 'string' || typeof item.data === 'string' || typeof item.path === 'string' || typeof item.file === 'string' || typeof item.url === 'string') result.push(item)
    else Object.values(item).forEach(child => outputValues(child, result))
  }
  return result
}

function imageSource(item: unknown): { image: string; rawUrl?: string } | null {
  if (typeof item !== 'object' || !item) return null
  const value = item as Record<string, unknown>
  const b64 = typeof value.b64_json === 'string' ? value.b64_json : typeof value.base64 === 'string' ? value.base64 : typeof value.data === 'string' && value.data.startsWith('data:') ? value.data : null
  if (b64) return { image: b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}` }
  const path = typeof value.path === 'string' ? value.path : typeof value.file === 'string' ? value.file : typeof value.url === 'string' ? value.url : null
  if (!path) return null
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return { image: path, rawUrl: path.startsWith('data:') ? undefined : path }
  return { image: apiUrl(`/v1/files?path=${encodeURIComponent(path)}`), rawUrl: path }
}

export async function callImageApi(opts: CallApiOptions): Promise<CallApiResult> {
  const profile = getActiveApiProfile(opts.settings)
  const payload: Record<string, unknown> = {
    prompt: opts.prompt,
    ...opts.params,
    profile: profile.id,
    images: opts.inputImageDataUrls,
  }
  if (opts.maskDataUrl) payload.mask = opts.maskDataUrl
  const response = await fetch(apiUrl('/v1/generate'), { method: 'POST', headers: headers(), body: JSON.stringify(payload) })
  const body = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) throw new Error(typeof body.error === 'string' ? body.error : `图片生成失败（HTTP ${response.status}）`)

  const candidates = outputValues(body.saved_images ?? body.images ?? body.data ?? body)
  const parsed = candidates.map(imageSource).filter((item): item is { image: string; rawUrl?: string } => Boolean(item))
  if (!parsed.length) throw new Error('接口返回成功，但没有找到输出图片')
  return {
    images: parsed.map(item => item.image),
    rawImageUrls: parsed.map(item => item.rawUrl).filter((item): item is string => Boolean(item)),
    actualParams: typeof body.actual_params === 'object' && body.actual_params ? body.actual_params as CallApiResult['actualParams'] : undefined,
    revisedPrompts: typeof body.revised_prompt === 'string' ? [body.revised_prompt] : undefined,
  }
}
