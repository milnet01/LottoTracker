# Working with the roadmap store

Read this before any `roadmap_log` write, any `roadmap_migrate`, and any
commit that touches `ROADMAP.md`. `CLAUDE.md` § Working conventions
points here.

**The roadmap DB is the source of truth, and `ROADMAP.md` is its rendered
output — migrated 2026-08-20 (`roadmap_migrate`, `ants-v1`, 33 items).**
So writes go through `roadmap_log` and reads through `roadmap_query`; the
file is no longer hand-edited, and a hand edit is reverted by the next write
rather than merged. Query one item by id instead of reading the file — at
1,600 lines that is the whole point of the change. This reverses the previous
convention, which had writes going in by hand precisely *because* the verb
re-renders the whole file; that re-render is now the mechanism enforcing one
roadmap standard across projects, not a defect to route around.
**The store is machine-local — `~/.local/share/ants-terminal/roadmap.sqlite`,
outside the repo and in no `.gitignore` — so the tracked `ROADMAP.md` is the
only thing that crosses machines.** Two consequences, both easy to get wrong.
**Re-run `roadmap_migrate` when that file changes underneath the store from
GIT** — a clone, a pull, a checkout, a revert — and always before the next
`roadmap_log` write. A write after an un-migrated pull reverts what you
pulled, and the large diff the next paragraph tells you to expect is exactly
what hides it. **Never re-migrate to pick up a local hand edit.** The store
cannot tell one from a pull, so migrating would launder into it precisely
what the rule above forbids.
**Tell the two apart before deciding, in this order.** `roadmap_query
check_sync:true` reports `file_in_sync` — false means the file and the store
disagree at all. Then `git status --porcelain ROADMAP.md`: non-empty means an
uncommitted edit — **and your own un-committed render of a `roadmap_log`
write looks exactly the same, so COMMIT that rather than discarding it.**
Discard (`git checkout -- ROADMAP.md`) only an edit made BY HAND, then
re-check; clean means the difference arrived as a commit, so re-migrate.
Where a hand edit and a pull are both present, discard the hand edit before
migrating — taking it in the other order launders the edit.
**A hand edit that was already committed is indistinguishable from a pull**;
there is no test for it, so do not commit one. And **commit
the re-rendered `ROADMAP.md` with the work it records**: the render is the
only copy that leaves this machine, an uncommitted one is a lost item, and
nothing catches it — the gate checks what a push contains, never what it
omits. A session with no
Ants MCP cannot write at all, and leaves the file alone rather than
hand-editing.
**Two things that follow, and neither is optional.** Any write re-renders all
1,600 lines, so a status flip that changes nothing still produces a large
diff. Review it by checking that every REMOVED line's text still appears
somewhere in the new file, **comparing with markup and trailing full stops
stripped from both sides** — the renderer rewrites both deliberately (below),
so a raw comparison flags dozens of correct lines and teaches you to wave the
check through, which is the one habit it exists to prevent. A census of ids,
statuses and word count is not a substitute: dropping a full stop moves none
of those three. And **a `Layman:` line must be ONE sentence**: the renderer
keeps only the first and discards the rest permanently — and **write it with
no trailing full stop**, because a bold `**Layman:**` line can lose one on any
render (4 of the 7 in this file did). That one is a standing authoring rule,
not a one-off: it applies to every `Layman:` line written from now on, and to
no other line. The id-dialect
normalisation *is* one-off — the two dialects this file had accumulated
collapse into one on the first render and never again. Ids, statuses, nested
sub-bullets and their
indentation all survive (measured 2026-08-20 in an isolated copy, filed as
Ants MCP feedback).
