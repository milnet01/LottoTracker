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

import os
import ssl
import sys

# Where distributions keep the trusted certificates, in one file.
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu, Arch
    "/etc/pki/tls/certs/ca-bundle.crt",    # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",              # openSUSE
    "/etc/ssl/cert.pem",                   # Alpine, Void
)


def use_host_certificates():
    """Point the bundled OpenSSL at this system's certificates (LOTTO-0102).

    The bundle's OpenSSL comes from the build system (Ubuntu) and looks where
    Ubuntu keeps them. Elsewhere that folder is missing, every HTTPS fetch
    fails verification, and no result can be checked. A value the user set wins.
    """
    if "SSL_CERT_FILE" in os.environ or "SSL_CERT_DIR" in os.environ:
        return
    default = ssl.get_default_verify_paths()
    if (default.cafile and os.path.isfile(default.cafile)) or (
            default.capath and os.path.isdir(default.capath)):
        return
    for path in CA_BUNDLES:
        if os.path.isfile(path):
            os.environ["SSL_CERT_FILE"] = path
            return


def main(argv):
    use_host_certificates()  # first: every branch's children inherit it
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
