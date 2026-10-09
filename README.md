# Hermes wall clock

A small Python plugin that adds a fresh clock to every Hermes turn through the
supported `pre_llm_call` hook. It works with the CLI and gateway, including a
gateway running in Kubernetes. Runtime code uses only Python's standard library.

Example model-visible context:

```text
[Wall clock at turn start: Friday, October 09, 2026 — 3:15 PM EDT (America/New_York, UTC-04:00)]
[Session began: 2026-10-03; 6 calendar days elapsed]
Use this turn's wall clock over earlier clocks and the frozen context-rebuild date.
```

The clock refreshes once per user/agent turn, before the tool loop. A long-running
turn retains its start time. It does not wake the agent or start extra turns.
`ZoneInfo` applies DST rules, including the repeated hour on November 1, 2026;
the UTC offset disambiguates that hour. The clock relies on the host's system
clock being correct.

Session age comes from Hermes's original `Conversation started:` line in system
context. It counts calendar-date boundaries, rather than complete 24-hour
periods. It keeps working on resume/restart/compaction when Hermes keeps that
anchor. Missing or unrecognized anchors produce `Session age: unknown`.
Future anchors produce a clock/anchor check message. No session IDs, databases,
conversation files, or plugin state are changed.

The built-in rebuild date remains in the system prompt: the supported hook adds
current-turn context and cannot remove it. The new text explicitly supersedes
it. Historical injected clocks may remain in Hermes's API replay history, so
the guidance also identifies this turn's clock as the current reference.

## Install in her profile

Requires Python 3.9+ and a Hermes version with `pre_llm_call` context returns and
`ctx.get_config()`. The container must have IANA timezone data (normally the OS
`tzdata` package). A missing or invalid timezone causes a visible plugin load
error rather than silently using UTC.

Put `__init__.py` and `plugin.yaml` together in:

```text
<HER_ACTIVE_HERMES_HOME>/plugins/wall-clock/
```

Use the home/profile used by **her gateway process**. A local installation or a
different profile will not configure her pod. Merge this into that profile's
existing `config.yaml`; preserve existing enabled plugins and settings:

```yaml
timezone: America/New_York
plugins:
  enabled:
    - wall-clock
  entries:
    wall-clock:
      settings:
        timezone: America/New_York
```

If `wall-clock` is listed under `plugins.disabled`, remove that entry. Check
that `HERMES_TIMEZONE`, if set in the workload, also equals `America/New_York`:
it overrides Hermes's top-level timezone. Aligning Hermes's timezone and this
plugin's timezone keeps the date-only birth anchor and calendar age consistent.
Settings are read at registration, so restart after configuration changes.

Before restarting, run in the container using its Hermes environment and actual
profile home (substitute the path):

```sh
HERMES_HOME=/actual/profile/home hermes plugins doctor /actual/profile/home/plugins/wall-clock --ci
```

If the installed release lacks `plugins doctor`, inspect `hermes plugins list`
after startup and use the standard-library tests below. Then send her a normal
message asking for the clock and session age. That checks live model delivery;
Doctor alone checks loading/registration. No separate clock tool is added.

## Kubernetes: survive pod replacement

Use a ConfigMap for the two runtime files, or include them in the container
image. A one-off `kubectl cp` into an ephemeral container filesystem disappears
when Kubernetes replaces the pod.

From this unpacked plugin directory, choose her namespace and create/update the
ConfigMap:

```sh
NAMESPACE=replace-with-her-namespace
kubectl -n "$NAMESPACE" create configmap hermes-wall-clock \
  --from-file=__init__.py --from-file=plugin.yaml \
  --dry-run=client -o yaml | kubectl apply -f -
```

Merge the following entries into her Deployment/StatefulSet pod template. Add
the mount to **her Hermes container**, preserving all existing containers,
mounts, and volumes. Replace the example mount path with her active profile
home followed by `/plugins/wall-clock`:

```yaml
# spec.template.spec.volumes: append this entry
- name: hermes-wall-clock
  configMap:
    name: hermes-wall-clock

# spec.template.spec.containers[her-Hermes-container].volumeMounts: append
- name: hermes-wall-clock
  mountPath: /actual/profile/home/plugins/wall-clock
  readOnly: true
```

Mount the directory rather than individual files with `subPath`. Keep the
profile configuration changes in the source that owns that file: Helm/GitOps,
a configuration ConfigMap, or the profile's persistent volume. Do not replace
the whole profile configuration with the minimal example above.

Apply the workload change through your normal deployment workflow, then restart
her gateway workload after later code/config updates, for example:

```sh
WORKLOAD=deployment/replace-with-her-workload
kubectl -n "$NAMESPACE" rollout restart "$WORKLOAD"
kubectl -n "$NAMESPACE" rollout status "$WORKLOAD"
```

Run Doctor in the selected pod/container, check startup logs for load errors,
and check her next response. For rollback, remove `wall-clock` from the enabled
list in the managed profile config and restart the gateway. Existing sessions
do not need deletion or reset.

## Tests and verification

```sh
python -m unittest discover -s tests -v
hermes plugins doctor . --ci
```

The optional integration test uses Hermes's internal test/Doctor machinery,
so it is tied to the checked release; the runtime plugin uses only documented
plugin APIs. Run it with Hermes's Python environment and an isolated test home:

```sh
HERMES_HOME=/tmp/hermes-wall-clock-test-home \
HERMES_WALL_CLOCK_INTEGRATION=1 \
python -m unittest discover -s tests -v
```

Verified on 2026-10-09 against local Hermes commit `2536772301`:

- 13 unit tests passed: formatting, both DST transitions, midnight rollover,
  age/anchor handling, configuration, and history preservation.
- 1 integration test passed: real plugin loader/dispatcher and production
  turn-context injection, with two turns crossing midnight and no LLM request.
- Hermes Plugin Doctor passed with one registered hook and zero tools.
- Hermes plugin validation passed for the manifest, config schema, and declared
  registrations.

No live Kubernetes workload was changed or tested.

References: [Hermes hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
and [plugin development](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).
