import subprocess
import sys


def copy_art(source: str, dest: str) -> None:
    try:
        from mediafile import Image, MediaFile
    except ImportError:
        return

    try:
        images = MediaFile(source).images or []
    except Exception:
        return
    if not images:
        return

    try:
        target = MediaFile(dest)
        if target.images:
            return          # the encoder already carried art across
        target.images = [Image(data=image.data, desc=image.desc,
                               type=image.type) for image in images]
        target.save()
    except Exception:
        pass


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: python -m tuney.convert_encoder SOURCE DEST COMMAND...",
              file=sys.stderr)
        return 2

    source, dest, command = argv[0], argv[1], argv[2:]
    returncode = subprocess.run(command).returncode
    if returncode != 0:
        # beets removes `dest` and reports the failure; art is moot.
        return returncode
    copy_art(source, dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
