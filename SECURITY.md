# Security model

This project is a password-protected, single-administrator test portal for trusted RCSS team binaries. Forks may deploy independent instances. It is **not** a public anonymous binary execution platform.

- Keep the web service behind HTTPS and use a unique long Arena password.
- Source code and Actions workflow logs in the public project are visible to everyone.
- Team uploads, config, results and logs belong in a separate **private** repository. Runtime checks reject public repositories. Never change its visibility or publish its contents.
- Do not upload sensitive team files to public commits, public Actions artifacts or public releases. `.gitignore` reduces accidental commits but is not an access-control mechanism.
- Use limited fine-grained PATs, expiry dates and separate storage/Render credentials. Store tokens only in GitHub Actions secrets or Render secret environment variables. Do not give untrusted users workflow editing rights.
- The normal runner sends team stdout/stderr into private files, not public console logs. It does not claim to prevent an intentionally malicious binary from accessing runner files, network or credentials. Player processes have no dedicated secure sandbox; removing secret environment variables is only defense in depth.
- Public logs may reveal infrastructure metadata. API/download requests require the Arena administrator login. All logged-in users share the administrator's data access; there is no per-user isolation.
- ZIP validation rejects traversal, symlinks, special files and oversized extraction. Linux shared libraries must be packed as regular files.
- A shared service open to arbitrary users requires per-job isolation, separate credentials outside execution environments, account-level authorization and abuse controls before launch.

If a secret is exposed, revoke it immediately and replace it. Removing it from the latest commit does not remove it from Git history.
