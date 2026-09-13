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

const ECONOMY_EVENT_HISTORY_LIMIT = 20;

/**
 * `count` increments on every message (safe as a "something changed" effect
 * dependency); `events` is capped to the most recent messages so a
 * long-lived economy page doesn't accumulate an unbounded history.
 */
export function useEconomySSE() {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const es = new EventSource("/api/economy/stream");

    const handler = (name: string) => (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [...prev, { event: name, data }].slice(-ECONOMY_EVENT_HISTORY_LIMIT));
        setCount((prev) => prev + 1);
      } catch {
        /* ignore malformed */
      }
    };

    ["reputation_update", "proof_recorded"].forEach((name) =>
      es.addEventListener(name, handler(name))
    );
    es.onerror = () => {
      es.close();
    };

    return () => es.close();
  }, []);

  return { events, count };
}
