# Diagram Maintenance Notes

All diagrams referenced by `../system_architecture.md` are now embedded directly into
the Markdown as PlantUML or Mermaid fenced blocks. This keeps the source next to the
explanatory text and eliminates the need for generated PNGs.

## Inline Diagram Conventions

* **PlantUML**: Architecture views (platform overview, ingestion, agent flow, etc.) now use
  only the built-in PlantUML shapes (component, database, queue, collections, etc.) so there
  are zero external dependencies or sprite downloads.
* **Mermaid**: Conceptual graphs (Graph State Model, Data Layer ERD) remain in Mermaid syntax,
  copied verbatim into the Markdown.

## Previewing

* **VS Code / GitHub**: Use a Markdown preview extension with PlantUML + Mermaid support.
* **Static image export**: Run `plantuml` or `mmdc` against the fenced code blocks if you
  need PNG/SVG artifacts for slide decks. Generated assets should live outside of `src/docs`
  to keep the Markdown canonical.
