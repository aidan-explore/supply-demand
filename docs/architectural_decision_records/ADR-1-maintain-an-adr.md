---
id: ADR-1
title: Architectural decision records
date: 2022/11/12 
status: Accepted
---

# Challenge
How do we capture the decisions we make as we develop the supply-demand data application?

# Additional Context

We require a lightweight mechanism to document important architectural decisions in a systematic manner for contributors to understand the current state of the codebase.

# Decision

We will capture code-related decision records in this directory as markdown files, and broader ecosystem decisions in Notion, [here](https://www.notion.so/explore-ai/ADRs-e9167ccbe86048c792fded54ea21844d)

For the records in this directory, each record will be in its own markdown file containing a [yaml front matter](https://assemble.io/docs/YAML-front-matter.html) block containing:
1. `id`: enumerated id number of the form `ARD-x`
2. `title`: title of the ADR
3. `date`: date when the ADR was posed
4. `status`: one of Proposed, Accepted, Deprecated, Superceded
5. `superceeded by`: optional field if status is `Superceded` containing value of the superceding ADR id.

In following, there will be H1 headings for `Challenge`, `Additional Context`, `Decision` and `Consquences` as shown in this record itself.

The filename stem will be the id.

# Consequences

All future ADRs will be  captured in this format within the directory:
`docs/architectural_design_records/`, in the format described above.


