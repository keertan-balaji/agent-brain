# OpenAI Codex / AGENTS.md spec

The `AGENTS.md`-at-repo-root convention is honored by OpenAI Codex and a growing set of other agents. It's the most portable single file.

## Install per repo

```bash
cp /home/keertan/codes/brain/clients/agent-instructions.md ./AGENTS.md
```

That's it. Any agent that follows the AGENTS.md spec — Codex, the cross-vendor agent runtimes, and increasingly Cursor / Continue / Cline — will pick up the brain conventions.

## Symlink for many repos

If you want one source of truth across many repos:

```bash
ln -s /home/keertan/codes/brain/clients/agent-instructions.md ./AGENTS.md
```

The symlink updates everywhere when you edit the canonical file.

## Existing AGENTS.md?

If the repo already has an `AGENTS.md` with project-specific content, **don't overwrite it.** Append the brain instructions as a new section, or copy them into a subsection like `## External knowledge — brain` so they coexist with the existing content.
