import codecs
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError


ATTACHMENT_MAX_FILE_SIZE = 25 * 1024 * 1024
PROJECT_IMAGE_MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ORIGINAL_FILE_NAME_LENGTH = 255
MAX_OFFICE_ARCHIVE_ENTRIES = 10_000
MAX_OFFICE_UNCOMPRESSED_SIZE = 100 * 1024 * 1024


@dataclass(frozen=True)
class ValidatedFileMetadata:
    original_file_name: str
    file_type: str
    mime_type: str
    file_size: int


_EXTENSION_TYPES = {
    ".pdf": ("pdf", "application/pdf"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".png": ("png", "image/png"),
    ".webp": ("webp", "image/webp"),
    ".docx": (
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".xlsx": (
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".csv": ("csv", "text/csv"),
    ".txt": ("txt", "text/plain"),
}


def _safe_original_name(name):
    normalized = str(name or "").replace("\\", "/")
    safe_name = PurePosixPath(normalized).name
    if not safe_name or safe_name in {".", ".."}:
        raise ValidationError("A valid original file name is required.")
    if len(safe_name) > MAX_ORIGINAL_FILE_NAME_LENGTH:
        raise ValidationError("The original file name is too long.")
    return safe_name


def _read_prefix(uploaded_file, length=8192):
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        return uploaded_file.read(length)
    finally:
        uploaded_file.seek(position)


def _validate_binary_signature(file_type, prefix):
    signatures = {
        "pdf": prefix.startswith(b"%PDF-"),
        "jpeg": prefix.startswith(b"\xff\xd8\xff"),
        "png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP",
    }
    if file_type in signatures and not signatures[file_type]:
        raise ValidationError("The file content does not match its extension.")


def _validate_text(uploaded_file, prefix):
    if prefix.startswith((b"MZ", b"\x7fELF", b"#!")) or b"\x00" in prefix:
        raise ValidationError("Executable or binary content is not allowed as text.")

    lowered = prefix.lstrip().lower()
    if lowered.startswith((b"<!doctype html", b"<html", b"<svg", b"<script")):
        raise ValidationError("HTML, SVG, and script content is not allowed.")

    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        decoder = codecs.getincrementaldecoder("utf-8")()
        while True:
            chunk = uploaded_file.read(64 * 1024)
            if not chunk:
                break
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise ValidationError("Text and CSV files must be valid UTF-8.") from exc
    finally:
        uploaded_file.seek(position)


def _validate_office_container(uploaded_file, file_type):
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            entries = archive.infolist()
            names = {entry.filename.lower() for entry in entries}

            if len(entries) > MAX_OFFICE_ARCHIVE_ENTRIES:
                raise ValidationError("The Office document contains too many entries.")
            if sum(entry.file_size for entry in entries) > MAX_OFFICE_UNCOMPRESSED_SIZE:
                raise ValidationError("The Office document expands beyond the allowed size.")
            if "[content_types].xml" not in names:
                raise ValidationError("The Office document structure is invalid.")
            if any(name.endswith("vbaproject.bin") for name in names):
                raise ValidationError("Macro-enabled Office documents are not allowed.")

            required_prefix = "word/" if file_type == "docx" else "xl/"
            if not any(name.startswith(required_prefix) for name in names):
                raise ValidationError("The Office document content does not match its extension.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValidationError("The Office document container is invalid.") from exc
    finally:
        uploaded_file.seek(position)


def inspect_attachment_file(uploaded_file, *, max_size=ATTACHMENT_MAX_FILE_SIZE):
    """Validate file content and return authoritative metadata."""
    safe_name = _safe_original_name(getattr(uploaded_file, "name", ""))
    extension = PurePosixPath(safe_name).suffix.lower()
    try:
        file_type, mime_type = _EXTENSION_TYPES[extension]
    except KeyError as exc:
        raise ValidationError("This file extension is not allowed.") from exc

    file_size = getattr(uploaded_file, "size", None)
    if not isinstance(file_size, int):
        position = uploaded_file.tell()
        try:
            uploaded_file.seek(0, 2)
            file_size = uploaded_file.tell()
        finally:
            uploaded_file.seek(position)

    if file_size <= 0:
        raise ValidationError("Empty files are not allowed.")
    if file_size > max_size:
        raise ValidationError("The file exceeds the allowed size.")

    prefix = _read_prefix(uploaded_file)
    _validate_binary_signature(file_type, prefix)

    if file_type in {"docx", "xlsx"}:
        _validate_office_container(uploaded_file, file_type)
    elif file_type in {"csv", "txt"}:
        _validate_text(uploaded_file, prefix)

    return ValidatedFileMetadata(
        original_file_name=safe_name,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
    )


def validate_attachment_file(uploaded_file):
    inspect_attachment_file(uploaded_file)
