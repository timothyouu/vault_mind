import { NextRequest, NextResponse } from "next/server";
import { readFileSync, readdirSync } from "fs";
import { join } from "path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export interface VaultNode {
  id: string;
  type: string;
  title: string;
  created: string;
  source_tool: string;
  status: string;
  related: string[];
  flags: string[];
  body: string;
}

function parseNode(content: string): VaultNode | null {
  const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return null;

  const frontmatter = match[1];
  const body = match[2].trim();

  const get = (key: string) => {
    const m = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
    return m ? m[1].trim() : "";
  };

  const getList = (key: string): string[] => {
    const start = frontmatter.indexOf(`\n${key}:`);
    if (start === -1) return [];
    const after = frontmatter.slice(start + key.length + 2);
    const lines = after.split("\n");
    const items: string[] = [];
    for (const line of lines) {
      if (line.startsWith("  - ")) items.push(line.slice(4).replace(/^"|"$/g, ""));
      else if (items.length > 0) break;
    }
    return items;
  };

  return {
    id: get("id"),
    type: get("type"),
    title: get("title").replace(/^"|"$/g, ""),
    created: get("created"),
    source_tool: get("source_tool"),
    status: get("status"),
    related: getList("related"),
    flags: getList("flags"),
    body,
  };
}

export async function GET(_req: NextRequest) {
  const repoRoot = process.env.REPO_ROOT ?? join(process.cwd(), "..");
  const nodesDir = join(repoRoot, "vault", "nodes");

  try {
    const files = readdirSync(nodesDir).filter((f) => f.endsWith(".md"));
    const nodes: VaultNode[] = [];
    for (const file of files) {
      const content = readFileSync(join(nodesDir, file), "utf8");
      const node = parseNode(content);
      if (node) nodes.push(node);
    }
    nodes.sort((a, b) => (b.created > a.created ? 1 : -1));
    return NextResponse.json({ nodes });
  } catch {
    return NextResponse.json({ nodes: [] });
  }
}
