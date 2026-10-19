/**
 * Model-category constants. Labels live in the i18n catalogue under
 * `admin.models.category.*`; consumers resolve via `t(MODEL_CATEGORY_KEY[cat])`.
 */
import type { MessageKey } from '@/lib/i18n/types'

export const MODEL_CATEGORY_KEY: Record<string, MessageKey> = {
  chat: 'admin.models.category.chat',
  embedding: 'admin.models.category.embedding',
  multimodal: 'admin.models.category.multimodal',
  ocr: 'admin.models.category.ocr',
  image_gen: 'admin.models.category.image_gen',
  asr: 'admin.models.category.asr',
  tts: 'admin.models.category.tts',
  rerank: 'admin.models.category.rerank',
}
