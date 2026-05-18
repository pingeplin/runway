# Common Failure Modes in Design Docs

These are the recurring ways design docs fail in the wild. Each is followed by a concrete before/after, because abstract advice ("be specific") doesn't help — patterns do.

When critiquing a draft, scan for these first. When writing one, read the draft back asking "did I do any of these?"

---

## 1. Solution disguised as problem

The "problem" section actually states a chosen solution. The real problem — what's broken in the world — never gets named. This makes alternatives impossible to evaluate, because they're being measured against a solution rather than a problem.

**Bad:**
> ## Problem
> We need to add Redis caching to the search endpoint.

**Better:**
> ## Problem
> Search p95 latency is 850ms. The target for this quarter is <200ms. Profiling shows 80% of time is spent in Postgres query planning for queries that repeat within 60-second windows. About 60% of search traffic is queries seen in the last minute.

The "better" version makes Redis one possible answer, not the only one. A reviewer can now ask: "what about query plan caching? read replicas? a different DB?" and the doc has a basis for answering.

---

## 2. Straw-man alternatives

Alternatives are listed but each is dismissed in two lines with reasons that any informed reader can tell are weak. The doc looks like it considered options; in reality the author had already decided.

**Bad:**
> **Alternative: PostgreSQL full-text search**
> - Cons: Slow, doesn't scale.
> - Why not chosen: We need something fast.

**Better:**
> **Alternative: PostgreSQL full-text search with materialized views**
> - We already run Postgres; no new infrastructure.
> - Materialized views could precompute the heavy aggregations, getting p95 to ~400ms in our benchmarks.
> - Why not chosen: 400ms still misses our 200ms target. We could close the gap with read replicas + caching, but at that point we're rebuilding what OpenSearch gives us out of the box, and we'd own the operational burden. Stack rank: OpenSearch is the better long-term answer despite the cost.

A reviewer reading the second version can disagree productively. The first version offers nothing to push back on.

**A useful test:** if you removed the chosen solution from the doc and asked someone to pick from the alternatives alone, would any be defensible? If not, they're straw men.

---

## 3. Hidden trade-offs

Every section says the chosen option wins. No downsides named. This is a sign the author either hasn't thought about what they're giving up, or has but is hiding it because they want approval. Reviewers learn to distrust these docs; experienced approvers will ask "what's the catch?" and force the author to invent a trade-off on the spot.

**Bad:**
> The proposed architecture is more performant, more scalable, easier to operate, and lower cost than the alternatives.

**Better:**
> The proposed architecture trades operational complexity (we now own an OpenSearch cluster) for query performance and scaling headroom. We're accepting roughly 2 weeks of additional ops setup and a permanent ~$3K/month infra cost in exchange for getting under our latency target and supporting projected 3x traffic growth without re-architecting again.

The second version names the price. A reviewer who thinks the price is too high knows where to push. The first version forces them to be the bad guy.

---

## 4. Open questions as escape hatches

"Open question: how will we handle X?" — where X, if answered the wrong way, would invalidate the entire design. These aren't open questions; they're unaddressed risks dressed up to look manageable.

**Bad:**
> **Open Questions**
> - [ ] How do we handle multi-region failover?
> - [ ] What's the migration plan for existing data?
> - [ ] How do we keep the cache consistent with writes?

If "we don't know how to keep the cache consistent" is open, the design is incomplete — cache consistency is the whole problem of a cache.

**Better:**
> **Open Questions** (genuinely small, won't change the design)
> - [ ] What's the right TTL — 30s or 60s? Will tune based on hit-rate measurements post-launch.
>
> **Risks we're accepting** (decisions made, named so reviewers can push back)
> - We're using cache-aside with a 60s TTL. This means inventory updates can be stale for up to 60s. Product team has confirmed this is acceptable; if it isn't, we'd switch to write-through, which costs us ~50ms of write latency.

The split between "genuinely uncertain small things" and "decisions made that have downsides" is what reviewers need.

---

## 5. Vague success criteria

"Improve performance," "increase reliability," "make the system more scalable." Not measurable. The doc cannot fail, which means it cannot succeed. Six months later no one can answer "did the project work?"

**Bad:**
> **Success Metrics**
> - Improved search performance
> - Better user experience
> - Increased scalability

**Better:**
> **Success Metrics** (measured 30 days post-launch)
> - p95 search latency: baseline 850ms → target <200ms
> - Search-to-purchase conversion: baseline 4.1% → target +0.5pp (i.e., 4.6%+)
> - Cluster sustains 50K QPS at <300ms p95 in load testing (3x current peak)

Every metric has a baseline, a target, and a measurement plan. "Better UX" can become a metric (NPS, satisfaction score) but must be pinned.

---

## 6. Scope creep mid-doc

The doc starts as "add caching to search." By page 5, it's also redesigning the indexing pipeline, proposing a new analytics dashboard, and suggesting we migrate off Postgres for product data. Each addition is plausible on its own, but together they make the doc unreviewable — the approver can't approve some parts and reject others.

**The fix:** when you find yourself widening scope while writing, stop. Either:
- Cut the addition and note it as out-of-scope ("Postgres migration is a separate question; see future RFC").
- If the addition is load-bearing for the original problem, the original scope was wrong — rename the doc and shrink it elsewhere.

A clear "Out of Scope" section is the cheap way to enforce this. Use it.

---

## 7. Template completionism

Every section is filled in. The doc is structurally complete. But there's no argument — every section restates the framing without committing to a position. Common in AI-generated drafts and in docs written by authors who treated the template as the goal.

**Symptoms:**
- Section headings are also the first sentence ("The goal of this design is to design...")
- "Trade-offs" section lists trade-offs without picking sides ("We could do X or Y; both have merits")
- "Alternatives" section describes alternatives without explaining why they were rejected
- The doc could be summarized as "we will build a thing that solves the problem" with no specifics

**The fix:** delete sections that don't carry an argument. A 3-page doc that takes a position beats a 10-page doc that doesn't.

---

## 8. Implementation in disguise

The doc spends pages on internal class hierarchies, helper functions, and detailed sequencing — content that belongs in the code or in implementation tickets. Approvers don't care; they care about the contract and the trade-off. Implementers can read the code.

**Bad:** 40 lines of Python showing how the cache wrapper class is structured.

**Better:** A 5-line interface showing the API the rest of the system sees, plus one paragraph explaining the cache-aside pattern. Implementation lives in code review, not the design doc.

A useful rule: if you'd be embarrassed to leave a section unchanged after the implementation finishes, it's probably implementation detail dressed up as design.

---

## 9. Unstated assumptions

The whole design rests on something the author considers obvious — read-write ratio, traffic pattern, data size, team capacity, an upstream system's behavior — but never names. Six months in, when the assumption breaks, no one remembers it was load-bearing.

**The fix:** every design has at least one. Name it.

> **Key assumption:** This design assumes read traffic continues to outnumber write traffic by ~100:1. If write volume grows (e.g., we add user-generated reviews), the cache invalidation cost may dominate and we'd revisit the cache-aside choice.

Now if writes grow, someone can search for "assumption" in the doc and find the trigger.

---

## 10. Doc-too-late, doc-too-early

**Too late:** the doc is written after the code is mostly built, to satisfy a process requirement. Reviewers can't actually push back; the design is fixed. The doc is theatre.

**Too early:** the doc is written before the author understands the problem. Alternatives are speculative, trade-offs are guessed, and the doc commits the team to a path before exploration would have shown a better one.

**The fix:** docs are most valuable when there's a real decision still open and the author has done enough exploration to evaluate alternatives credibly. If you're writing one and you can't honestly say "I would change my mind based on review feedback," consider whether you should be writing it at all. If you're writing one and you don't have a hypothesis yet, run `/proto` first to spike, then come back to `/design`.

---

## Quick self-check before sharing a draft

A short list to run through:

1. Can a reader find the proposed decision in the first paragraph?
2. Do the alternatives have plausible champions, or are they straw men?
3. Have I named at least one trade-off the chosen approach accepts?
4. Is the riskiest assumption stated explicitly?
5. Do success metrics have baselines and targets?
6. Could this doc be 30% shorter without losing argument?
7. If a reviewer pushes back on the chosen approach, where in the doc is the answer?

If any answer is "no" or "I'm not sure," fix that before sharing.
