# Custom pipeline stage (5 minutes)

## Goal

Add a new step without forking `PipelineSurveillance`.

## Steps

1. Implement a processor with `@EvilEyeBase.register("MyStage")` (see `identity_pass.py`).
2. Prefer subclassing `DualModeProcessor` for thread/process lifecycle.
3. Use `pipeline_class: PipelineDeclarative` and list stages in JSON (`config_declarative.json`).
4. Ensure the module is imported before `create_instance` (e.g. `PYTHONPATH=examples/custom_pipeline_stage`).

```bash
PYTHONPATH=examples/custom_pipeline_stage:$PYTHONPATH \
  evileye run examples/custom_pipeline_stage/config_declarative.json --no-gui
```

## Touch matrix

| Goal | Files to touch |
|------|----------------|
| New detector/tracker same slot | one module + `@register` + JSON `type` |
| New stage in graph | module + Declarative `stages[]` (or fork Surveillance) |
| Process/GPU stage | `DualModeProcessor` + `MpWorker` (see `docs/developing_dual_mode_modules.md`) |
| Events / DB / GUI | see `examples/custom_event_detector/` |
