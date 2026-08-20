# Normalization Hash Test Fixtures

Cross-platform test cases ensuring all implementations produce identical hashes.

## Fixture Types

### Text Fixtures
Test text normalization: `normalizeText(text) → hash`

### Image Fixtures
Test full OCR pipeline: `image → OCR → cleanOcrArtifacts → normalizeText → hash`

## File Format

**Filename:** `{expected-sha256-hash}.md` (or `PLACEHOLDER-*.md` for new fixtures)

### Text Fixture
```markdown
---
description: Brief description of what this tests
charNormalization: "éè→e" (optional)
---
The actual text to normalize goes here.
```

### Image Fixture
```markdown
---
description: Brief description of what this tests
---
![](pics/image-filename.png)
```

Image files are stored in the `pics/` subdirectory.

## How Tests Work

### Text Fixtures
1. Parse body text from markdown
2. Call `normalizeText(body, metadata)`
3. Compute SHA-256 hash
4. Assert hash equals filename

### Image Fixtures
1. Detect `![](pics/path.png)` in body
2. Load image and run OCR (ML Kit on Android, Vision on iOS)
3. Apply `cleanOcrArtifacts()` then `normalizeText()`
4. Compute SHA-256 hash
5. Assert hash equals filename

## Platform Support

| Platform | Text Fixtures | Image Fixtures |
|----------|--------------|----------------|
| JS/Web | Unit tests | N/A (no browser OCR) |
| Android | Unit tests | Instrumented tests (ML Kit) |
| iOS | Unit tests | Instrumented tests (Vision) |

## Adding New Image Fixtures

1. Add image file to the `pics/` subdirectory
2. Create `PLACEHOLDER-{name}.md` pointing to `pics/{image}.png`
3. Run Android instrumented tests: `adb push normalization-hashes /sdcard/ && ./gradlew connectedAndroidTest`
4. Tests will log the ML Kit hash - rename the `.md` file to `{hash}.md`

## Running Android Instrumented Tests

```bash
# Push fixtures to device/emulator
adb push normalization-hashes /sdcard/

# Run instrumented tests
./gradlew connectedAndroidTest
```
