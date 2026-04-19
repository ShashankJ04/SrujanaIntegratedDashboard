/* Dashboards API Client
   Cookie-based auth — cookies are sent automatically by the browser.
   Port of frontend/src/api/client.ts */

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    credentials: 'same-origin',
    ...options,
  });

  if (res.status === 401 || res.status === 403) {
    window.location.href = '/login';
    throw new Error('Authentication required');
  }

  if (!res.ok) {
    let errMsg;
    try {
      const errBody = await res.json();
      errMsg = errBody.message || `API error: ${res.status}`;
    } catch {
      errMsg = res.statusText || `API error: ${res.status}`;
    }
    throw new Error(errMsg);
  }

  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    return res.json();
  }
  return res;
}

async function apiPost(path, body) {
  return apiFetch(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

async function apiPatch(path, body) {
  return apiFetch(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

async function apiPut(path, body) {
  return apiFetch(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

async function apiDelete(path) {
  return apiFetch(path, { method: 'DELETE' });
}

/**
 * Post a FormData (for file uploads).
 */
async function apiPostForm(path, formData) {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    body: formData,
  });
  if (res.status === 401 || res.status === 403) {
    window.location.href = '/login';
    throw new Error('Authentication required');
  }
  if (!res.ok) {
    let errMsg;
    try { errMsg = (await res.json()).message; } catch { errMsg = res.statusText; }
    throw new Error(errMsg || `API error: ${res.status}`);
  }
  return res.json();
}

/**
 * Download a file via POST (for Excel exports).
 */
async function apiDownload(path, body, fileName) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    credentials: 'same-origin',
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let errMsg;
    try { errMsg = (await res.json()).message; } catch { errMsg = res.statusText; }
    throw new Error(errMsg || `Download error: ${res.status}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName || 'download.xlsx';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}

/**
 * Download a file via GET.
 */
async function apiDownloadGet(path, fileName) {
  return apiDownload(path, null, fileName);
}
