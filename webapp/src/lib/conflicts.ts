import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

// Assumes Next.js dev server is started from webapp/ — override via REPO_ROOT env var
const REPO_ROOT = process.env.REPO_ROOT ?? path.resolve(process.cwd(), "..");
// VAULT_NODES: prefer the real vault, fall back to fixtures when vault/nodes/ doesn't
// exist yet (e.g. running `npm run dev` standalone without the full stack started).
const _defaultVaultNodes = path.join(REPO_ROOT, "vault", "nodes");
const _fixtureVaultNodes = path.join(REPO_ROOT, "fixtures", "vault", "nodes");
const VAULT_NODES =
  process.env.VAULT_NODES ??
  (fs.existsSync(_defaultVaultNodes) ? _defaultVaultNodes : _fixtureVaultNodes);

export interface HunkLine {
  no: number;
  text: string;
}

export interface ConflictHunk {
  index: number;
  title: string;
  ours: string[];
  theirs: string[];
  oursLabel: string;
  theirsLabel: string;
  anchor: string;
}

export type Segment =
  | { type: "context"; lines: HunkLine[] }
  | { type: "conflict"; hunk: ConflictHunk };

export interface ConflictFile {
  id: string;
  displayName: string;
  title: string;
  sessionLabel: string;
  baseRef: string;
  headRef: string;
  segments: Segment[];
  hunkCount: number;
}

export interface ConflictSummary {
  id: string;
  displayName: string;
  title: string;
  hunkCount: number;
  sessionLabel: string;
}

// ---------------------------------------------------------------------------
// Git helpers
// ---------------------------------------------------------------------------

function shortSha(ref: string): string {
  try {
    return execFileSync("git", ["rev-parse", "--short", ref], {
      cwd: REPO_ROOT,
      encoding: "utf-8",
      timeout: 3000,
    }).trim();
  } catch {
    return ref.slice(0, 7);
  }
}

function gitRefs(): { base: string; head: string } {
  try {
    const head = shortSha("HEAD");
    const hasMergeHead = fs.existsSync(path.join(REPO_ROOT, ".git", "MERGE_HEAD"));
    const incoming = hasMergeHead ? shortSha("MERGE_HEAD") : "disk";
    return { base: head, head: incoming };
  } catch {
    return { base: "unknown", head: "unknown" };
  }
}

// ---------------------------------------------------------------------------
// Secret scanning — delegates to the one Python implementation per SPEC
// ---------------------------------------------------------------------------

export interface SecretHit {
  pattern_id: string;
  description: string;
  line: number;
  col: number;
  excerpt: string;
}

export function scanFile(absPath: string): SecretHit[] {
  // Do NOT silently return [] on Python failure — that would bypass the secret
  // scan entirely and allow writes that should be blocked. Throw instead so
  // resolveNode can surface the scan failure distinctly from "no secrets found".
  let out: string;
  try {
    out = execFileSync("python3", ["-m", "vaultmind.secrets", absPath], {
      cwd: REPO_ROOT,
      encoding: "utf-8",
      timeout: 8000,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Secret scan failed (python3 -m vaultmind.secrets): ${msg}`);
  }
  try {
    return JSON.parse(out) as SecretHit[];
  } catch {
    throw new Error(`Secret scanner returned non-JSON output: ${out.slice(0, 200)}`);
  }
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

function parseConflictContent(
  id: string,
  absPath: string,
  content: string
): ConflictFile | null {
  if (!content.includes("<<<<<<<")) return null;

  const titleMatch = content.match(/^title:\s*(.+)$/m);
  const title = titleMatch ? titleMatch[1].trim() : id;
  const refs = gitRefs();

  const lines = content.split("\n");
  const segments: Segment[] = [];
  let hunkIdx = 0;
  let sessionLabel = "incoming";

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("<<<<<<<")) {
      const oursLabel = line.replace(/^<<<<<<<\s*/, "") || "HEAD";
      const oursLines: string[] = [];
      const theirsLines: string[] = [];
      let inOurs = true;
      let theirsLabel = "incoming";

      i++;
      while (i < lines.length) {
        const cl = lines[i];
        if (cl.startsWith("=======")) {
          inOurs = false;
          i++;
          continue;
        }
        if (cl.startsWith(">>>>>>>")) {
          theirsLabel = cl.replace(/^>>>>>>>\s*/, "").trim();
          sessionLabel = theirsLabel;
          i++;
          break;
        }
        if (inOurs) oursLines.push(cl);
        else theirsLines.push(cl);
        i++;
      }

      segments.push({
        type: "conflict",
        hunk: {
          index: hunkIdx,
          title: `Hunk ${hunkIdx + 1}`,
          ours: oursLines,
          theirs: theirsLines,
          oursLabel,
          theirsLabel,
          anchor: `hunk-${hunkIdx}`,
        },
      });
      hunkIdx++;
    } else {
      const lineNo = i + 1;
      const last = segments[segments.length - 1];
      if (last?.type === "context") {
        last.lines.push({ no: lineNo, text: line });
      } else {
        segments.push({ type: "context", lines: [{ no: lineNo, text: line }] });
      }
      i++;
    }
  }

  if (hunkIdx === 0) return null;

  return {
    id,
    displayName: path.basename(absPath),
    title,
    sessionLabel,
    baseRef: refs.base,
    headRef: refs.head,
    segments,
    hunkCount: hunkIdx,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function listConflictedNodes(): ConflictSummary[] {
  if (!fs.existsSync(VAULT_NODES)) return [];
  return fs.readdirSync(VAULT_NODES)
    .filter((f) => f.endsWith(".md"))
    .flatMap((f) => {
      const absPath = path.join(VAULT_NODES, f);
      const content = fs.readFileSync(absPath, "utf-8");
      if (!content.includes("<<<<<<<")) return [];
      const parsed = parseConflictContent(f.replace(/\.md$/, ""), absPath, content);
      if (!parsed) return [];
      return [
        {
          id: parsed.id,
          displayName: parsed.displayName,
          title: parsed.title,
          hunkCount: parsed.hunkCount,
          sessionLabel: parsed.sessionLabel,
        },
      ];
    });
}

export function getConflictedNode(id: string): ConflictFile | null {
  if (!fs.existsSync(VAULT_NODES)) return null;
  const absPath = path.join(VAULT_NODES, `${id}.md`);
  if (!fs.existsSync(absPath)) return null;
  const content = fs.readFileSync(absPath, "utf-8");
  return parseConflictContent(id, absPath, content);
}

export function resolveNode(
  id: string,
  resolutions: Record<number, "ours" | "theirs" | "both">
): { ok: boolean; secretBlocked?: string; scanSnippet?: string } {
  const node = getConflictedNode(id);
  if (!node) return { ok: false };

  const resultLines: string[] = [];
  for (const seg of node.segments) {
    if (seg.type === "context") {
      resultLines.push(...seg.lines.map((l) => l.text));
    } else {
      const choice = resolutions[seg.hunk.index];
      if (choice === "ours") resultLines.push(...seg.hunk.ours);
      else if (choice === "theirs") resultLines.push(...seg.hunk.theirs);
      else if (choice === "both") {
        resultLines.push(...seg.hunk.ours, ...seg.hunk.theirs);
      }
    }
  }

  const merged = resultLines.join("\n");
  const absPath = path.join(VAULT_NODES, `${id}.md`);

  // Write to temp file, scan, then atomically write final
  const tmpPath = `${absPath}.vmtmp`;
  try {
    fs.writeFileSync(tmpPath, merged, "utf-8");
    const hits = scanFile(tmpPath);
    if (hits.length > 0) {
      // Clean up temp file before returning — don't leave .vmtmp on disk.
      try { fs.unlinkSync(tmpPath); } catch {}
      return {
        ok: false,
        secretBlocked: hits[0].description,
        scanSnippet: hits[0].excerpt,
      };
    }
    // Atomic rename
    fs.renameSync(tmpPath, absPath);
    return { ok: true };
  } catch (err: unknown) {
    try { fs.unlinkSync(tmpPath); } catch {}
    // Surface scan configuration failures (e.g. python3 not found) distinctly
    // from generic I/O errors so the caller can show a meaningful message.
    const msg = err instanceof Error ? err.message : "unknown error";
    return { ok: false, secretBlocked: msg };
  }
}
