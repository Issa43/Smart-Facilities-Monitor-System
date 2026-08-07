from django.core.files.storage import FileSystemStorage, storages


class ProtectedFileSystemStorage(FileSystemStorage):
    """Filesystem storage that cannot expose a direct public URL."""

    def url(self, name):
        raise ValueError(
            "Protected files do not have public URLs; use an authorized download."
        )


def get_protected_storage():
    """Return the storage alias that has no public URL."""
    return storages["protected"]
