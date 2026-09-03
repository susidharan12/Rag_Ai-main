const BASE = ''

async function json(res) {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch { /* keep statusText */ }
    throw new Error(detail)
  }
  return res.json()
}

export async function fetchDocuments() {
  return json(await fetch(`${BASE}/api/documents`))
}

export async function uploadFiles(files, onStage) {
  // Upload sequentially so each file gets its own report + progress card
  const results = []
  for (const file of files) {
    onStage?.(file.name, 'uploading')
    const form = new FormData()
    form.append('files', file)
    onStage?.(file.name, 'parsing')
    const res = await fetch(`${BASE}/api/documents`, {
      method: 'POST',
      body: form,
    })
    const data = await json(res)
    onStage?.(file.name, 'embedding')
    results.push({ file: file.name, ...data })
  }
  onStage?.(null, 'done')
  return results
}

export async function deleteDocument(docId) {
  return json(await fetch(`${BASE}/api/documents/${docId}`, { method: 'DELETE' }))
}

export async function askQuestion(question) {
  const res = await fetch(`${BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  return json(res)
}

export async function fetchHealth() {
  return json(await fetch(`${BASE}/api/health`))
}

export async function fetchBenchmark() {
  return json(await fetch(`${BASE}/api/benchmark`))
}
