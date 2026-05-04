import { fetchEventSource } from "@microsoft/fetch-event-source";

function parseData(text) {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function openEventStream(url, options = {}) {
  const queue = [];
  const waiters = [];
  const controller = new AbortController();
  let finished = false;
  let streamError = null;

  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  function push(item) {
    if (waiters.length > 0) {
      const next = waiters.shift();
      next(item);
      return;
    }
    queue.push(item);
  }

  function closeStream() {
    if (!finished) {
      finished = true;
      push(null);
    }
  }

  fetchEventSource(url, {
    method: options.method ?? "POST",
    headers: {
      Accept: "text/event-stream",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers ?? {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: controller.signal,
    openWhenHidden: true,
    onmessage(ev) {
      push({
        event: ev.event || "message",
        data: parseData(ev.data),
      });
    },
    onclose() {
      closeStream();
    },
    onerror(err) {
      streamError = err;
      closeStream();
      throw err;
    },
  }).catch((err) => {
    streamError = err;
    closeStream();
  });

  return {
    cancel() {
      controller.abort();
    },
    async *[Symbol.asyncIterator]() {
      while (true) {
        if (queue.length === 0) {
          const item = await new Promise((resolve) => waiters.push(resolve));
          if (item === null) {
            break;
          }
          yield item;
          continue;
        }
        const item = queue.shift();
        if (item === null) {
          break;
        }
        yield item;
      }
      if (streamError) {
        throw streamError;
      }
    },
  };
}
