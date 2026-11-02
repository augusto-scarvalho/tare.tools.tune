# Compact DSL workflow for agents

[Full reference](dsl.md) · [Corrected measurements](dsl-efficiency.md) · [Português](pt-BR/dsl-agentes.md)

Use the DSL for durable, inspectable source and guarded edits. Keep a warm Python session when a short existing API call solves the task. Compare cold setup, warm continuation and persisted transactions separately; the corrected results do not establish a universal token advantage.

For a render/listen/edit task, start with the [review loop](dsl-review.md):
`dsl review SOURCE --name NAME -o BUNDLES --json`, then
`dsl describe BUNDLE --fields FIELD --json`, then
`dsl edit SOURCE --from-bundle BUNDLE -o BUNDLES --set /PATH JSON --json`.
Each edit returns the next observed bundle. Use `--refine` for original root Voice
materialized controls; batch fields from one observation. Existing bundles can be
reviewed without regeneration. `dsl help TOPIC --json` provides progressive help.
Add `--response compact` to `review`/`edit` for routine feedback; request a detailed
review of the retained bundle only when needed. The [continuation analysis](dsl-review-token-costs.md)
counts both profiles for Python and the DSL over five real edits.
In a persistent Python tool namespace, bind fixed edit arguments once with
`functools.partial`; still pass the observed `from_bundle` explicitly on every
call. The linked analysis counts that setup and tests this pattern too.
The lower-level workflow below remains useful when only a query/patch is needed.

1. Discover only the domain and fields needed. A name-specific catalog is detailed; project it:

   ```bash
   tare.tools.tune dsl catalog --domain sfx --name ui --fields name,example,knobs.ring --json
   tare.tools.tune dsl catalog --domain transform --name transpose --fields example --json
   ```

2. Reuse definitions. Generate routine variants programmatically with immutable builders or `dsl variants`. Write the initial source once.

3. Read one authored target, with its revision:

   ```bash
   tare.tools.tune dsl query bank.tune.json --target sound:confirm_strong --fields fragment.with.power --response compact --json
   ```

   Projection supports up to 32 dictionary paths, four fields deep; no array indexing, wildcards or expressions. Select a deeper object with `--pointer` if necessary. Revision identities remain present.

4. Send a small revision-checked patch. Request only the acknowledgement needed for the next edit:

   ```bash
   tare.tools.tune dsl patch bank.tune.json --patch edit.json --response compact --json
   ```

   Keep revisions/guards in tool variables or retained files where possible. Use the revision associated with the inspected source. Never bypass a conflict by blindly substituting a fresh revision.

5. Expand only to discover primitive fields. If the exact CompileResult is already held in a persistent tool context, derive its guard with `materialized_id(compiled.plan)` and retain it as a variable. Keep the recipe and wrap the selected instance in `edit` once. Subsequent changes to an existing `/lowpass` override use the authored `/set/~1lowpass` path; preserve other overrides rather than replacing the whole recipe. Stale errors require explicit review. Ordinary authoring IDs and definition names do not seed synthesis; track names do.

6. Diagnose the requested window/stage with bounded rows:

   ```bash
   tare.tools.tune inspect bank.tune.json --name confirm_strong --view layers --top 3 --fields id,power --band 2000 6000 --no-pitch --response compact --json
   ```

   Use `--view stages` and `--node` for child stages. Request source/parameters only for the selected row. Use a saved bundle when analyzing an already captured revision; this avoids rebuilding it. Follow `next` when a result is truncated. `full` is an explicit request for the complete report.

The [earlier payloads](dsl-measurements.json) remain historical evidence of a more verbose procedure. Use the [version-2 report](dsl-efficiency.md) to assess equivalent memory/persisted services, compact envelopes and setup amortized over repeated edits. Fully counted reusable helpers are allowed to both Python and the DSL. A persistent tool context is not a free stateless CLI session.

The measured savings come from avoiding irrelevant source/report traffic. They do not establish lower total tokens than a competent Python helper. Count discovery, complete patches, guards, failures and repeated context when evaluating a workflow.
