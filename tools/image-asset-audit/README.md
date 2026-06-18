# image-asset-audit

Lightweight VVK Part A evidence collector for Phase7 reference images and Phase8.5 keyframe/storyboard-grid images.

The tool only collects deterministic evidence:

- File exists and opens.
- Width, height, format, mode, aspect ratio.
- Optional expected width/height checks.
- Optional expected aspect-ratio check.
- Optional grid panel boxes for storyboard grids.

It does not decide visual PASS/FAIL. OCR, face count, watermark/text overlay, and perceptual hash/embedding are soft-signal extensions and are currently reported as `NOT_AVAILABLE` until reliable implementations are added.

## Examples

Phase7 16:9 reference asset evidence:

```powershell
python C:\Users\Administrator\Desktop\tools\image-asset-audit\image_asset_audit.py `
  --image C:\path\to\R01_scene.png `
  --out-dir C:\path\to\project\image_audit\R01 `
  --profile phase7 `
  --expected-ratio 16:9
```

Phase8.5 2x3 storyboard grid evidence:

```powershell
python C:\Users\Administrator\Desktop\tools\image-asset-audit\image_asset_audit.py `
  --image C:\path\to\Clip2_grid.png `
  --out-dir C:\path\to\project\image_audit\Clip2_grid `
  --profile phase8.5 `
  --expected-ratio 16:9 `
  --grid 2x3
```

Outputs:

- `image_asset_audit_manifest.json`
- `image_asset_audit_evidence.md`

Use those files as VVK Part A evidence, then complete Part B visual judgment and Part C adversarial review when required.
