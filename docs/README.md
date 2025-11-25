# Design Documents

This directory contains the comprehensive design specifications for the Vizonomy platform.

## 📚 Reading Guide

We recommend reading the documents in the following order to build a progressive understanding of the system:

1.  **[System Architecture](overview/system_architecture.md)**: Start here. This document provides the high-level overview of the platform, core components, and data flow.
2.  **[Agent Architecture](agents/architecture.md)**: Dive into the LangGraph-based agent design, including the router, subgraphs, and state management.
3.  **[Schema & Persistence](data/schema_and_persistence.md)**: Understand the data model, including the dual-scope document system (base vs. user), deduplication logic, and knowledge graph tables.
4.  **[API Contracts](interfaces/api_contracts.md)**: Review the REST API specifications and event payloads that define the interface between the FastAPI Gateway and the LangGraph service.

## 📂 Directory Structure

*   **[overview/](overview/)**: High-level system design, architecture diagrams, and project status.
    *   `system_architecture.md`: The main design document (now holds inline PlantUML + Mermaid diagrams).
    *   `project_status.md`: Tracks pending definitions and roadmap items.
    *   `diagrams/`: Historical notes on diagram sources plus guidance for previewing the inline code blocks.
*   **[agents/](agents/)**: Detailed specifications for the AI agents.
    *   `architecture.md`: High-level agent design.
    *   `implementation.md`: Low-level implementation details (nodes, edges, state schema).
    *   `rag_blueprint.md`: Specifics of the RAG retrieval flow.
    *   `retrieval_config.md`: Configuration parameters for the retrieval system.
*   **[data/](data/)**: Database design and knowledge graph specs.
    *   `schema_and_persistence.md`: Detailed ERD and persistence rules.
    *   `knowledge_graph.md`: Primer on the GraphRAG implementation.
*   **[interfaces/](interfaces/)**: API and event definitions.
    *   `api_contracts.md`: REST API and event envelopes.

## 🚦 Status & Roadmap

For a current view of pending work, completed definitions, and the implementation roadmap, please refer to **[Project Status](overview/project_status.md)**.
