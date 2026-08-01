## ADDED Requirements

### Requirement: Local OCR transcription for chat image attachments
When the active chat model does not natively support image input, the system SHALL attempt local OCR transcription of an attached image before falling back to a Vision-Language model description.

#### Scenario: Text-only model receives an image of handwritten notes
- **WHEN** a user attaches an image to a chat session whose active model is not vision-capable (`model_supports_vision` returns `False`) and OCR is enabled
- **THEN** the system runs local PaddleOCR against the image and, if it returns non-empty transcribed text, inlines that text into the message sent to the model, labeled distinctly from a VL-model description

#### Scenario: OCR finds no usable text
- **WHEN** local OCR is attempted on an attached image and returns no text (blank result, exception, or below the accepted confidence threshold)
- **THEN** the system falls back to the existing Vision-Language description flow (`analyze_image_with_vl_result`) unchanged

#### Scenario: OCR dependency not installed
- **WHEN** the `paddlepaddle`/`paddleocr` packages are not installed or fail to import
- **THEN** the system skips the OCR step without raising an error and proceeds directly to the existing Vision-Language fallback, with no change to chat availability

### Requirement: OCR reuse for scanned PDF pages
The system SHALL apply the same local-OCR-first, VL-fallback order to image-heavy PDF pages that today call the Vision-Language model directly.

#### Scenario: PDF page with an embedded image and little extractable text
- **WHEN** `_process_pdf` encounters a page whose extracted text is under the existing sparse-text threshold and the page contains an image
- **THEN** the system attempts local OCR on that image before calling the Vision-Language model, using the OCR result if it returns usable text

### Requirement: User override takes precedence over OCR output
Cached OCR text SHALL be editable by the user through the existing chat attachment caption/OCR control, and a saved edit SHALL be treated as authoritative on subsequent turns.

#### Scenario: User corrects a misread word
- **WHEN** a user edits the cached text for an attachment via the chat attachment dropdown after OCR has populated it
- **THEN** subsequent turns in that session use the user-edited text instead of re-running OCR or the Vision-Language fallback

### Requirement: OCR settings controls
Administrators SHALL be able to enable/disable OCR and configure its recognition language via existing Settings, independent of whether a Vision-Language model is configured.

#### Scenario: OCR disabled by setting
- **WHEN** `ocr_enabled` is set to `false`
- **THEN** the system skips the OCR step entirely for both chat image attachments and PDF pages, going straight to the existing Vision-Language fallback

#### Scenario: Non-English handwriting
- **WHEN** `ocr_lang` is configured to a language other than the default and an attached image contains text in that language
- **THEN** local OCR runs using the configured language model rather than the default
