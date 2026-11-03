# Implementation Constraints

- Use Hexagonal Architecture. Domain code must not import web frameworks, database libraries, provider SDKs, Meta, MCP, or search clients.
- Product, Promotion, payment, shipping, availability, provenance, and Order ownership are deterministic services.
- Operational data uses typed parameterized repositories. Policy retrieval returns bounded passages with source file, document version, section, and page metadata.
- `LLMPort` and `LLMFactory` normalize provider messages, tool calls, results, usage, and capabilities. Unsupported capabilities fail before execution.
- `ToolRegistry` is allowlisted and schema-validated. Authorization is checked in the server-side use case, never delegated to the prompt.
- SQLite is the P0 persistence boundary. Ingestion is validated, idempotent, and atomic. Optional market observations never overwrite official Product data.
- Sessions own bounded history and identity isolation. Logs use correlation data without raw prompts or customer PII by default.
- `Decimal` is required for customer-visible monetary calculations. Exact rounding and unresolved commercial boundaries must be recorded before implementation.
- Optional WhatsApp, market, and MCP adapters reuse P0 use cases and cannot be required by the offline suite.
