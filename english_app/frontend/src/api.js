const BASE = '/api'
const get = path => fetch(`${BASE}${path}`).then(r => r.json())
const post = (path, body) => fetch(`${BASE}${path}`, {
  method: 'POST',
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify(body),
}).then(r => r.json())

export { get, post }
