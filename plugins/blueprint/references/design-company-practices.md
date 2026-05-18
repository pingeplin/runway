# Named Approaches

When a user invokes a specific named process — "the Amazon way," "PR/FAQ," "ADR," "tiered RFCs" — these are the operational distinctions that actually matter. Skip the encyclopedia; reach for the part that changes what to write.

---

## PR/FAQ (Amazon, "working backwards")

**Use when:** customer/user value is in doubt, or the project is product-driven and the team needs to align on what's worth building before how to build it.

**The mechanic:** write a press release as if the product already shipped. Then write the FAQ — both customer-facing questions and internal ones (cost, risk, dependencies). If the press release isn't compelling, that's a signal the project may not be worth doing.

**What changes in the doc:** the front page is narrative prose, written from the customer's perspective. Technical architecture comes later (often in a separate companion doc). Reviewers read for whether the *value* is real, not whether the *implementation* is sound.

---

## ADR (Architecture Decision Record)

**Use when:** the decision has already been made and you want to capture *why* for future engineers. Not for proposals; for archaeology.

**The mechanic:** terse, immutable, single-decision. Three sections: Context (why we had to choose), Decision (what we chose), Consequences (what this means going forward). Numbered (ADR-001, ADR-002...). When a new decision supersedes an old one, write a new ADR that says so — don't edit the old one.

**What changes in the doc:** brevity. ADRs are 1-2 pages. Future readers want to find one quickly and understand it without prerequisites. Keep one decision per ADR.

---

## Tiered RFCs (Uber-style, scale-driven)

**Use when:** the org is large enough that one-size-fits-all is too heavy for small changes and too light for cross-team ones.

**The mechanic:** different templates for different scopes. Team-scoped change = lightweight template, async review, fast turnaround. Cross-team or company-wide change = full template, named approvers, formal review meeting.

**What changes:** match weight to stakes. Don't make a one-engineer-week change use the full template. Don't let a quarter-long multi-team migration get away with a Mini RFC.

---

## Google-style Design Doc

**Use when:** the engineering org is the primary audience and the goal is decision-making with broad visibility.

**The mechanic:** no strict template, but the cultural norm is that *trade-offs are the point*. The first question when joining a project is "where's the design doc?" Docs become the entry point for understanding any system. Once shipped, amendments are appended (not rewritten) — the doc becomes a record of how thinking evolved.

**What changes:** lead with trade-offs, not solutions. Be willing to be wrong on the page; reviewers' job is to find what's wrong. Treat the doc as a living artifact early; freeze it after launch and append corrections.

---

## Stripe / writing-first culture

**Use when:** the team is async-first and writing quality is part of the engineering bar.

**The mechanic:** docs are required for non-trivial work, treated with the same care as external product docs, expected to go through multiple rounds of feedback. Authors are expected to update over the lifecycle.

**What changes:** the bar is higher. Less informal voice; more crafted prose. A doc that reads like a brain dump won't pass review.

---

## Squarespace "Yes, if"

**Use when:** the review culture is collaborative rather than gatekeeping.

**The mechanic:** reviewers default to "yes, if you address X" rather than "no." Architecture review is collaborative iteration, not approval gate.

**What changes:** authors expect to revise. Reviewers expect to suggest, not block. Useful framing if a team feels its review process has become combative.

---

## Picking the right one

If the user is asking which to adopt for their team:

- **Small team (< 20 engineers), no current process:** Mini RFCs by default, full RFCs for anything cross-team. Don't add formality you don't need yet.
- **Mid-size team (20-100), growing:** Tiered approach. Lightweight template for team-scope; heavier template with named approvers for org-wide.
- **Product-driven team:** Try PR/FAQ for new product directions. Use it as a forcing function for "is this worth building?"
- **Established team with existing process:** Mimic local convention. Don't impose a different format; reviewers are calibrated on what they see.
- **Recording past decisions:** ADRs. Numbered, terse, immutable.

A useful default for a team starting fresh: one lightweight RFC template, plus an ADR repo for capturing decisions. Add tiers only when the lightweight version starts feeling too thin for some changes.
