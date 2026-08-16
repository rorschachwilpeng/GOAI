# AgentTeams Technical Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a presentation-ready HTML diagram that combines a five-layer AgentTeams technical architecture with a single-message sequence diagram.

**Architecture:** Keep the existing React/Vite single-page artifact and replace only the visual composition. Model the architecture and sequence content as arrays in `App.jsx`; render all connectors and lanes with semantic HTML and CSS so the output remains responsive and screenshot-ready without adding dependencies.

**Tech Stack:** React 19, Vite 6, CSS Grid/Flexbox, existing Sites build adapter.

## Global Constraints

- Preserve the existing 16:9 presentation-board visual language.
- Do not add dependencies or modify hosting/worker/test infrastructure.
- Clearly distinguish current local components, cloud inference, and future optional components.
- The page must remain legible without scrolling at common desktop presentation sizes.

---

### Task 1: Replace the product stack with the technical architecture composition

**Files:**
- Modify: `src/App.jsx`

**Interfaces:**
- Consumes: existing React entry point importing `App`.
- Produces: `App()` rendering `.technical-board`, `.layer-stack`, and `.sequence-panel`.

- [ ] **Step 1: Define the five layer data objects** with concise component descriptions and local/optional status.
- [ ] **Step 2: Define sequence participants and eight ordered message events** covering input, persistence, context assembly, cloud inference, optional execution, and response.
- [ ] **Step 3: Render the header, left stack, right sequence, legends, and data-boundary footer** using semantic sections and articles.
- [ ] **Step 4: Run `npm run build`** and expect Vite to produce `dist/client/index.html` without JSX errors.

### Task 2: Implement the presentation visual system

**Files:**
- Modify: `src/styles.css`
- Modify: `index.html`

**Interfaces:**
- Consumes: class names produced by `App.jsx`.
- Produces: a responsive 16:9 board at desktop sizes and a vertically scrollable fallback below 900px.

- [ ] **Step 1: Rebuild the board layout** as a 56/44 two-column grid with consistent header and footer.
- [ ] **Step 2: Style the five layers** with distinct but restrained tones and three-line component cards.
- [ ] **Step 3: Style the sequence panel** with actor lifelines, numbered events, direction arrows, and local/cloud/execution/review color semantics.
- [ ] **Step 4: Add desktop compression and mobile fallback media queries** without hiding content.
- [ ] **Step 5: Change the document title** to `AgentTeams 分层技术架构`.
- [ ] **Step 6: Run `npm run build && npm run test:sites`** and expect all commands to pass.

### Task 3: Visual verification

**Files:**
- Verify: local Vite page at `http://localhost:4173/`

**Interfaces:**
- Consumes: built React/CSS artifact.
- Produces: a browser-verified layout suitable for a screenshot.

- [ ] **Step 1: Start the Vite server** with `npm run dev -- --host 127.0.0.1`.
- [ ] **Step 2: Inspect the page at desktop dimensions** and verify no clipping, overlap, or unreadable type.
- [ ] **Step 3: Correct only observed layout defects** and rerun the build and Sites tests.
- [ ] **Step 4: Open the final page in the user's browser**.
