# EvilEye example plugin package

This small distribution registers an item processor through the
`evileye.plugins` entry point. Install it into the same Python environment as
EvilEye with:

```powershell
python -m pip install -e .
```

Then restart EvilEye and add `example/add-label` to a supported
`PipelineSurveillance` module group. The example processor accepts either a
`[data, frame]` pair or a plain mapping and returns the corresponding updated
item. It supports `thread` and `process` execution; process mode requires the
plugin package to remain importable in the EvilEye environment.

The complete SPI and configuration reference is in [`docs/PLUGINS.md`](../../docs/PLUGINS.md).
