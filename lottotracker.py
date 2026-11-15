"""The frozen build's entry point (LOTTO-0015 §4.2). Nothing imports this file.

In the AppImage there are no .py files to start, so supervise.child_command()
starts this same program with the helper's name as its first argument:

    lottotracker            -> the tray
    lottotracker serve      -> the local page's server
    lottotracker watch ...  -> the SMS watcher (--once passed through)

Each branch imports its own module inside the branch, so the serve and watch
children never load Qt (LOTTO-0013 INV-19's reason). An unknown argument exits
rather than starting a tray: a spawn that still passed a script path would
otherwise start a tray, which spawns two more.
"""

import sys


def main(argv):
    if len(argv) < 2:
        import tray
        return tray.main()
    name = argv[1]
    if name == "serve":
        import serve
        return serve.main()
    if name == "watch":
        import watch_sms
        # watch_sms.main() reads sys.argv[1:] for --once.
        sys.argv = [argv[0], *argv[2:]]
        return watch_sms.main()
    sys.stderr.write(f"lottotracker: unknown argument {name!r}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
