# Analyze Image Example

```bash
curl -X POST "http://localhost:8000/analyze-image" \
  -F "image=@sample.jpg" \
  -F 'targets_json=["ACME-4491","Inspection Passed","Serial Number","06/10/2026"]' \
  -F "match_threshold=85"
```

The server runs OCR once for the uploaded image, builds match candidates from the OCR boxes,
and returns the best fuzzy match for each target string.

