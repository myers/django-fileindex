import hashlib, base64, subprocess, os, shutil, filecmp

import logging

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
    results = hash_file(filepath)
    results["mime_type"] = get_mime_type(filepath)
    results["size"] = os.path.getsize(filepath)
    return results


def hash_file(filepath):
    f = open(filepath, "rb")
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()

    for piece in read_in_chunks(f):
        sha1.update(piece)
        sha512.update(piece)
    return {
        "sha1": str(base64.b32encode(sha1.digest()), "ascii"),
        "sha512": str(base64.b32encode(sha512.digest()), "ascii"),
    }


def get_mime_type(filepath):
    file_proc = subprocess.Popen(
        ["/usr/bin/file", "--mime-type", "--brief", filepath], stdout=subprocess.PIPE
    )
    (
        stdout,
        stderr,
    ) = file_proc.communicate()
    if file_proc.returncode != 0:
        raise Exception(
            "'file' didn't work %r %r"
            % (
                stdout,
                stderr,
            )
        )
    return str(stdout, "ascii").strip()


def on_same_filesystem(src, dst):
    logger.debug(f"on_same_filesystem({src!r}, {dst!r})")

    src_st_dev = os.lstat(src).st_dev
    if os.path.exists(dst):
        dst_st_dev = os.lstat(dst).st_dev
    else:
        dst_dir = os.path.dirname(dst)
        while not os.path.exists(dst_dir):
            logger.debug(f"{dst_dir!r} doesn't exists looking at parent")
            dst_dir = os.path.dirname(dst_dir)
        logger.debug(f"found {dst_dir}")
        dst_st_dev = os.lstat(dst_dir).st_dev
    return src_st_dev == dst_st_dev


def smartadd(src, dst, only_hard_link=False):
    if os.path.exists(dst) and os.path.samefile(src, dst):
        return True

    if on_same_filesystem(src, dst):
        return smartlink(src, dst)

    if only_hard_link:
        raise CannotHardLinkError(
            f"{src} and {dst} not on the same filesystem, cannot hardlink"
        )
    return smartcopy(src, dst)


def smartcopy(src, dst):
    logger.debug(f"smartcopy({src!r}, {dst!r})")
    assert os.path.exists(src)
    if os.path.exists(dst):
        assert same_contents(
            src, dst
        ), f"These two files should be the same, but are not {src!r} vs {dst!r}"
        return False
    dst_dir = os.path.dirname(dst)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    shutil.copy2(src, dst)
    return True


def summary_of_file(filepath):
    first_20_bytes = None
    with open(filepath, "rb") as ff:
        first_20_bytes = ff.read(20)
    size = os.path.getsize(filepath)

    hashs = hash_file(filepath)
    print(
        f"{filepath} has this at the beginning {first_20_bytes!r} and is {size} bytes big, and hashs {hashs!r}"
    )


def same_contents(file1, file2):
    if filecmp.cmp(file1, file2):
        return True

    print("These two files aren't the same: ")
    summary_of_file(file1)
    summary_of_file(file2)


def smartlink(src, dst):
    logger.debug(f"smartlink({src!r}, {dst!r})")
    assert os.path.exists(src)
    if os.path.exists(dst):
        assert same_contents(
            src, dst
        ), f"These two files should be the same, but are not {src!r} vs {dst!r}"
        logger.debug(
            f"src {src!r} is the same as dst {dst!r}, unlinking src, and adding a hardlink at src that points to dest"
        )

        os.unlink(src)
        # we want to link the dst to the src, as the dst might have many other hard links
        os.link(dst, src)
        return
    dst_dir = os.path.dirname(dst)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    os.link(src, dst)


class CannotHardLinkError(Exception):
    pass
