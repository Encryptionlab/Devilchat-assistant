/* API client for backend endpoints */

const BASE = '';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function sendMessage(
  message: string,
  chatHistory: { role: string; content: string }[]
) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message, chat_history: chatHistory }),
  });
}

export async function sendMessageStream(
  message: string,
  chatHistory: { role: string; content: string }[],
  onEvent: (type: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, chat_history: chatHistory }),
    signal,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let eventType = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const dataStr = line.slice(6);
        if (eventType && dataStr) {
          try {
            const data = JSON.parse(dataStr);
            onEvent(eventType, data);
          } catch {
            // skip unparseable
          }
        }
        eventType = '';
      }
    }
  }
}

export async function getConversations() {
  return request<{
    active: Record<string, unknown> | null;
    closed: Record<string, unknown>[];
  }>('/api/conversations');
}

export async function getRelationship() {
  return request<Record<string, unknown>>('/api/relationship');
}

export async function updateRelationship(data: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/relationship', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function bootstrap(description: string) {
  return request<Record<string, unknown>>('/api/bootstrap', {
    method: 'POST',
    body: JSON.stringify({ description }),
  });
}
