"""python -m get_haiggoh_tui — run the TUI app (entered via bin/get-haiggoh-tui)."""
import sys

from .app import GetHaiggohApp


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    unknown = [a for a in argv if a != "--resume"]
    if unknown:
        sys.stderr.write(f"usage: python -m get_haiggoh_tui [--resume] "
                         f"(unrecognized: {' '.join(unknown)})\n")
        return 2
    GetHaiggohApp(resume="--resume" in argv).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
