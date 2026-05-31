const BASE = '/api'

// 단어 생성처럼 오래 걸리는 요청도 있어 기본 타임아웃을 넉넉히(120s) 둔다.
async function request(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${BASE}${path}`, { ...options, signal: controller.signal })
    try {
      return await res.json()
    } catch {
      // 비 JSON 응답(프록시/게이트웨이 타임아웃 HTML 등)
      return { detail: `서버 응답 오류 (${res.status})` }
    }
  } finally {
    clearTimeout(timer)
  }
}

const get = (path, timeoutMs) => request(path, {}, timeoutMs)

const post = (path, body, timeoutMs) => request(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}, timeoutMs)

export { get, post }
