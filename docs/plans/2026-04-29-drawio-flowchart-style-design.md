# 2026-04-29 Drawio Thesis Flowchart Style Design

## Goal
Update the local `drawio-skill` so that future Chinese thesis flowchart requests default to a strict academic black-and-white flowchart style. Synchronize the same rules and example into the project repository for traceability.

## Scope
- Add a dedicated Chinese thesis flowchart reference document.
- Add a default example image for that flowchart style.
- Update `SKILL.md` so requests like `流程图`, `软件流程图`, and `程序流程图` load this reference automatically.
- Copy the same reference and example into the project repository under `docs/`.

## Rules To Encode
- White background, black borders, no color, no shadow.
- Start and end must use terminator nodes.
- Process nodes use rectangles; decision nodes use diamonds.
- Node boxes of the same type should stay the same size.
- Use orthogonal connectors only.
- Connectors must not cross, must not pass through nodes, and should avoid overlapping node borders.
- Do not add unnecessary decorative titles inside the figure unless the user asks.
- Branch loops should return directly to meaningful workflow nodes, not placeholder nodes like `重新采集` unless the user explicitly requires such a node.

## Repository Sync
Store a mirrored copy of the reference and the example image in the project repo under `docs/diagram-rules/` so the rule set is versioned with the project.
