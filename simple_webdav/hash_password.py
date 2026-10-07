from __future__ import annotations

import getpass

import bcrypt


def main():
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    print(bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii"))


if __name__ == "__main__":
    main()
