/**
 * webapp/src/components/AgentChat.tsx
 *
 * Drop-in chat panel for talking to the Fetch.ai agent.
 * Styled with the same glassmorphic tokens as the rest of VaultMind.
 *
 * Usage — add anywhere in your page:
 *   import AgentChat from "@/components/AgentChat";
 *   <AgentChat />
 */

"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { useAgent } from "@/lib/useAgent";

const SANS = "var(--font-space-grotesk), system-ui, sans-serif";
const MONO = "var(--font-jetbrains-mono, 'JetBrains Mono', monospace)";

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function SendIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <path
        d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AgentIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
      <path
        d="M4 20c0-4 3.6-7 8-7s8 3 8 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      style={{ animation: "spin 0.8s linear infinite" }}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="40"
        strokeDashoffset="15"
        strokeLinecap="round"
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------

interface Message {
  role: "user" | "agent" | "error";
  text: string;
  ts: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AgentChat() {
  const { send, reply, loading, error, reset } = useAgent();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Append agent reply or error to history when it arrives
  useEffect(() => {
    if (reply) {
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: reply, ts: new Date().toISOString() },
      ]);
      reset();
    }
  }, [reply, reset]);

  useEffect(() => {
    if (error) {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: error, ts: new Date().toISOString() },
      ]);
      reset();
    }
  }, [error, reset]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", text, ts: new Date().toISOString() },
    ]);
    await send(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  function fmtTime(iso: string) {
    try {
      return new Date(iso).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 420,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        backdropFilter: "blur(var(--blur))",
        WebkitBackdropFilter: "blur(var(--blur))",
        boxShadow: "var(--glass-shadow)",
        overflow: "hidden",
        fontFamily: SANS,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "12px 16px",
          borderBottom: "1px solid var(--border-muted)",
          background: "var(--surface-2)",
        }}
      >
        <span style={{ color: "var(--accent)", display: "inline-flex" }}>
          <AgentIcon />
        </span>
        <span
          style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}
        >
          Fetch.ai Agent
        </span>
        <span
          style={{
            marginLeft: 4,
            fontSize: 10,
            fontFamily: MONO,
            color: "var(--faint)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: 200,
          }}
        >
          agent1qvlz2w…5vnkyy8
        </span>
        <div style={{ flex: 1 }} />
        {/* Live indicator */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            padding: "2px 8px",
            borderRadius: 9999,
            fontSize: 10,
            fontFamily: MONO,
            background: "var(--green-dim)",
            color: "var(--green)",
            border: "1px solid rgba(116,224,168,0.32)",
          }}
        >
          <span
            style={{
              width: 5,
              height: 5,
              borderRadius: "50%",
              background: "var(--green)",
              boxShadow: "0 0 6px var(--green)",
            }}
          />
          agentverse
        </span>
      </div>

      {/* Message history */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              margin: "auto",
              textAlign: "center",
              color: "var(--faint)",
              fontSize: 13,
            }}
          >
            Send a message to the agent.
            <br />
            <span style={{ fontSize: 11, fontFamily: MONO }}>
              Replies are async — usually 2–5 s.
            </span>
          </div>
        )}

        {messages.map((msg, i) => {
          const isUser = msg.role === "user";
          const isError = msg.role === "error";
          return (
            <div
              key={i}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: isUser ? "flex-end" : "flex-start",
                animation: "vm-fade 0.2s ease",
              }}
            >
              <div
                style={{
                  maxWidth: "80%",
                  padding: "9px 13px",
                  borderRadius: isUser
                    ? "14px 14px 4px 14px"
                    : "14px 14px 14px 4px",
                  fontSize: 13,
                  lineHeight: 1.55,
                  color: isError ? "var(--red)" : "var(--text)",
                  background: isUser
                    ? "var(--accent-btn)"
                    : isError
                    ? "var(--red-dim)"
                    : "var(--surface-2)",
                  border: `1px solid ${
                    isUser
                      ? "rgba(138,166,255,0.4)"
                      : isError
                      ? "rgba(255,138,138,0.3)"
                      : "var(--border)"
                  }`,
                  backdropFilter: "blur(8px)",
                  WebkitBackdropFilter: "blur(8px)",
                  wordBreak: "break-word",
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg.text}
              </div>
              <span
                style={{
                  marginTop: 3,
                  fontSize: 10,
                  color: "var(--faint)",
                  fontFamily: MONO,
                }}
              >
                {isUser ? "you" : isError ? "error" : "agent"} ·{" "}
                {fmtTime(msg.ts)}
              </span>
            </div>
          );
        })}

        {/* Typing indicator */}
        {loading && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              color: "var(--muted)",
              fontSize: 12,
              animation: "vm-fade 0.2s ease",
            }}
          >
            <SpinnerIcon />
            Agent is thinking…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input row */}
      <div
        style={{
          padding: "12px 14px",
          borderTop: "1px solid var(--border-muted)",
          background: "var(--surface-2)",
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the agent… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={loading}
          style={{
            flex: 1,
            resize: "none",
            background: "var(--inset)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "8px 12px",
            color: "var(--text)",
            fontSize: 13,
            fontFamily: SANS,
            lineHeight: 1.5,
            outline: "none",
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)",
            opacity: loading ? 0.6 : 1,
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          aria-label="Send"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 38,
            height: 38,
            borderRadius: 10,
            border: "1px solid rgba(138,166,255,0.4)",
            background: "var(--accent-btn)",
            color: "var(--text)",
            cursor: loading || !input.trim() ? "not-allowed" : "pointer",
            opacity: loading || !input.trim() ? 0.5 : 1,
            flexShrink: 0,
            transition: "opacity 0.15s",
          }}
        >
          {loading ? <SpinnerIcon /> : <SendIcon />}
        </button>
      </div>
    </div>
  );
}