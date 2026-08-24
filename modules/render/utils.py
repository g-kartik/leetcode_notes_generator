from enum import StrEnum


class FileVariant(StrEnum):
    REMOTE = "remote"  # Will use the markdown with remote(internet) image urls
    LOCAL = "local"  # Will use the markdown with locally saved image urls(local relative paths)
    ALL = "all" # Generate both
