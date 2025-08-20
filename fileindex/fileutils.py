import base64
import filecmp
import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def read_in_chunks(file_object, chunk_size=1024):
    """Lazy function (generator) to read a file piece by piece.
    Default chunk size: 1k."""
    while True:
        data = file_object.read(chunk_size)
        if not data:
            break
        yield data


def analyze_file(filepath):
    path = Path(filepath)
    results = hash_file(filepath)
    results["mime_type"] = get_mime_type(filepath)
    results["size"] = path.stat().st_size
    return results


def hash_file(filepath):
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()

    with open(filepath, "rb") as f:
        for piece in read_in_chunks(f):
            sha1.update(piece)
            sha512.update(piece)
    return {
        "sha1": str(base64.b32encode(sha1.digest()), "ascii").rstrip("="),
        "sha512": str(base64.b32encode(sha512.digest()), "ascii").rstrip("="),
    }


def get_mime_type(filepath):
    try:
        result = subprocess.run(
            ["/usr/bin/file", "--mime-type", "--brief", filepath],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise Exception(f"'file' didn't work {result.stdout!r} {result.stderr!r}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception(f"'file' command timed out for {filepath!r}") from None


def on_same_filesystem(src, dst):
    logger.debug(f"on_same_filesystem({src!r}, {dst!r})")

    src_path = Path(src)
    dst_path = Path(dst)

    src_st_dev = src_path.stat().st_dev
    if dst_path.exists():
        dst_st_dev = dst_path.stat().st_dev
    else:
        dst_parent = dst_path.parent
        while not dst_parent.exists():
            logger.debug(f"{dst_parent!r} doesn't exists looking at parent")
            dst_parent = dst_parent.parent
        logger.debug(f"found {dst_parent}")
        dst_st_dev = dst_parent.stat().st_dev
    return src_st_dev == dst_st_dev


def smartadd(src, dst, only_hard_link=False):
    src_path = Path(src)
    dst_path = Path(dst)
    if dst_path.exists() and src_path.samefile(dst_path):
        return True

    if on_same_filesystem(src, dst):
        return smartlink(src, dst)

    if only_hard_link:
        raise CannotHardLinkError(f"{src} and {dst} not on the same filesystem, cannot hardlink")
    return smartcopy(src, dst)


def smartcopy(src, dst):
    logger.debug(f"smartcopy({src!r}, {dst!r})")
    src_path = Path(src)
    dst_path = Path(dst)
    assert src_path.exists()
    if dst_path.exists():
        assert same_contents(src, dst), f"These two files should be the same, but are not {src!r} vs {dst!r}"
        return False
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def summary_of_file(filepath):
    path = Path(filepath)
    first_20_bytes = None
    with open(filepath, "rb") as ff:
        first_20_bytes = ff.read(20)
    size = path.stat().st_size

    hashs = hash_file(filepath)
    print(f"{filepath} has this at the beginning {first_20_bytes!r} and is {size} bytes big, and hashs {hashs!r}")


def same_contents(file1, file2):
    if filecmp.cmp(file1, file2):
        return True

    print("These two files aren't the same: ")
    summary_of_file(file1)
    summary_of_file(file2)


def smartlink(src, dst):
    logger.debug(f"smartlink({src!r}, {dst!r})")
    src_path = Path(src)
    dst_path = Path(dst)
    assert src_path.exists()
    if dst_path.exists():
        assert same_contents(src, dst), f"These two files should be the same, but are not {src!r} vs {dst!r}"
        logger.debug(
            f"src {src!r} is the same as dst {dst!r}, unlinking src, and adding a hardlink at src that points to dest"
        )

        src_path.unlink()
        # we want to link the dst to the src, as the dst might have many other
        # hard links
        src_path.hardlink_to(dst_path)
        return
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.hardlink_to(src_path)


class CannotHardLinkError(Exception):
    pass
