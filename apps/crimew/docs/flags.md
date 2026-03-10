# Guidance for contributors — adding and using feature flags

When to use a flag (rules)

- Prefer feature code with no user-visible on/off switch. Flags are usually temporary for pre-launch testing.
- Use a permanent flag only when:
  - Support/QA needs to ask users to flip it to diagnose problems (e.g. ignore-gpu-blocklist style).
  - QA/dev environments need to toggle behavior and command-line switches are impractical (mobile/packaged builds).
- Do NOT add a permanent flag just because “users might want to turn it off.” If users need that control, make it a setting.
- “Developers/QA might need to turn it on/off” is valid justification for a permanent flag.
- Avoid flags for core UX decisions that will ship enabled for all users long-term; prefer staged rollouts instead.

Naming & design conventions

- id: lower_snake_case, short, unique, prefixed by area when useful (e.g. network_prefetch_experiment).
- name: short human label.
- description: single-paragraph intent + risk/impact sentence.
- choices: always include a "default" choice; include explicit "enabled"/"disabled" choices if boolean-like, and other option ids for variants.
- default field: reflects the product default (string id of a choice). UI maps "Default" → the default behavior (not always "enabled").
- Keep each flag focused (one change surface per flag).

How to add a flag (repo-specific)

1. Add the flag JSON to flags.json (follow existing structure). Example snippet to append:

````json
// ...existing code...
{
  "id": "net_prefetch_experiment",
  "name": "Network prefetch experiment",
  "description": "Enables experimental network prefetch heuristics for faster navigation. May increase bandwidth use.",
  "default": "disabled",
  "choices": [
    { "id": "default", "name": "Default", "description": "Use standard prefetch behavior." },
    { "id": "enabled_aggressive", "name": "Enable (aggressive)", "description": "Use aggressive prefetch heuristics." },
    { "id": "enabled_safe", "name": "Enable (safe)", "description": "Use conservative prefetch heuristics." },
    { "id": "disabled", "name": "Disabled", "description": "Do not prefetch." }
  ]
}
// ...existing code...
````

1. The UI (FlagsDialog) reads flags.json via flags.get_flags_cached(), so no UI code change is required for basic add/remove unless you need custom presentation.

How to read a flag in code

- For boolean-like checks use resolve_bool_flag(flag_id, default_value)
- For multi-choice use get_experiment_choice(flag_id) and switch on the returned choice id.
- To persist a choice programmatically, call set_experiment_choice(flag_id, choice_id).

Example usage (Python):

````python
# ...existing code...
from flags import resolve_bool_flag, get_experiment_choice, set_experiment_choice

# boolean behavior
if resolve_bool_flag("net_prefetch_experiment", default_value=False):
    enable_prefetch()

# multi-choice behavior
choice = get_experiment_choice("net_prefetch_experiment")
if choice == "enabled_aggressive":
    set_prefetch_mode("aggressive")
elif choice == "enabled_safe":
    set_prefetch_mode("safe")
else:
    set_prefetch_mode("standard")

# persist from code / tests:
set_experiment_choice("net_prefetch_experiment", "enabled_safe")
# ...existing code...
````

## UI considerations

- Flag UI shows display names and maps each combo entry to the internal choice id. Ensure choices have distinct display names and helpful descriptions.
- Keep long descriptions wrapped and accessible (tooltips or inline text).
- Flags are applied after Save; document in the dialog when changes require restart.