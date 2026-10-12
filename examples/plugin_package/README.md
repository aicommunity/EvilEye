# EvilEye example plugin package

This small distribution registers both an item processor and a custom pipeline
through the `evileye.plugins` entry point. Install it into the same Python
environment as EvilEye with:

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

Then restart EvilEye so it discovers the entry point. Add
`example/add-label` to a supported `PipelineSurveillance` module group to
use the processor.

## Verify an external pipeline

From this directory, run:

```powershell
python smoke_pipeline.py
```

The smoke creates `example/marker-pipeline` through `PipelineService`, passes
configuration through `PipelineDependencies`, initializes and starts it,
processes one item, and stops/releases it. Expected output includes
`{'marker': 'external-package', 'sequence': 1}`. This pipeline is deliberately
small and has no camera/model dependencies; it demonstrates plugin discovery
and the complete `IPipeline` lifecycle.

The example processor accepts either a `[data, frame]` pair or a plain mapping
and returns the corresponding updated item. It supports `thread` and
`process` execution; process mode requires the plugin package to remain
importable in the EvilEye environment.

The complete SPI and configuration reference is in
[`docs/PLUGINS.md`](../../docs/PLUGINS.md).
