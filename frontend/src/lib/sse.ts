import { useEffect, useRef, useState } from "react";

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export function useSSE(goalId: string | undefined, active: boolean) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!goalId || !active) return;

    const es = new EventSource(`/api/goals/${goalId}/stream`);
    esRef.current = es;

    const handler = (name: string) => (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [...prev, { event: name, data }]);
      } catch {
        /* ignore malformed */
      }
    };

    const eventNames = [
      "goal_status",
      "task_update",
      "task_done",
      "task_waiting",
      "credential_request",
      "goal_done",
      "tool_call",
      "tool_result",
      "message",
      "ping",
    ];

    eventNames.forEach((name) => es.addEventListener(name, handler(name)));
    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [goalId, active]);

  return events;
}
