---
name: remote-server
title: Remote server (SSH / SFTP / FTP)
title_tr: Uzak sunucu (SSH / SFTP / FTP)
title_en: Remote server (SSH / SFTP / FTP)
description: Connects to a server the user gives, finds and reads files, runs and tests commands, uploads and downloads files over SSH, SFTP or FTP.
description_tr: Kullanıcının verdiği sunucuya bağlanır; dosyaları bulur, okur, komut çalıştırıp test eder, SSH, SFTP veya FTP ile dosya yükler ve indirir.
description_en: Connects to a server the user gives, finds and reads files, runs and tests commands, uploads and downloads files over SSH, SFTP or FTP.
tools: run, write_file, read_file, edit_file, list_dir, todo, fetch_url
---
Work on the server the user named, with the host, port, user and key or password the user gave. Never store
credentials in files of the project: pass them through environment variables of one `run` call
(`env` field or os.environ in the script) and never print them.

## Connect (Python, paramiko; works on Windows, macOS, Linux)
```python
import os, paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(os.environ["H"], port=int(os.environ.get("P", 22)), username=os.environ["U"],
          password=os.environ.get("PW"), key_filename=os.environ.get("KEY"), timeout=15)
def sh(cmd):
    _, o, e = c.exec_command(cmd, timeout=120); code = o.channel.recv_exit_status()
    return code, o.read().decode(errors="replace"), e.read().decode(errors="replace")
print(sh("uname -a; whoami; pwd"))
sftp = c.open_sftp()   # sftp.listdir, sftp.get(remote, local), sftp.put(local, remote), sftp.open(path).read()
```
One script per step (connect, do, print a short result, close). OpenSSH also works: `ssh -o BatchMode=yes`,
`scp`, `sftp -b`. FTP: Python's ftplib (FTP_TLS when available).

## Work
1. Learn the server first: OS, web root, running services (`systemctl list-units --type=service --state=running`,
   `ss -tlnp`), disk (`df -h`), logs (`journalctl -n 100`, nginx/apache error logs).
2. Find files with `find / -name ... 2>/dev/null | head`, `grep -rn` limited to the app folder.
3. Before changing a file: download a backup copy (sftp.get) into the chat folder. Edit locally, upload, then
   verify (service status, `curl -I` the site, tail the error log).
4. Destructive commands (rm -rf, dropping databases, restarting production services, firewall changes) need the
   user's explicit request for that exact action.
5. Report what was checked, changed (with backup paths) and verified.
