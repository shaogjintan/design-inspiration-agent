# Hosting FORMA on AWS Lightsail

Step-by-step, from your laptop to a working site. The server installs itself with
[`deploy/lightsail.sh`](lightsail.sh); you mostly click through the AWS console and
paste a few commands.

**Before you start:** the server downloads the code from GitHub. Anything not
committed and pushed will not be on the site.

---

## 0. On your laptop: push the code and mark the live version

```bash
cd "~/Desktop/Y3S1/NUS-ISS Hackathon/design-inspiration-agent"
git add -A
git commit -m "Describe what changed"
git push origin Develop/GL-api

git tag -f live            # the version to put online: here, what you just committed
git push -f origin live
```

To put an older version online instead, tag that commit, e.g. `git tag -f live 8b3998b`.

## 1. Get into AWS

1. Accept the sandbox invitation email, then sign in to the **AWS access portal**.
2. Open your lease's account, choose the console role, and search for **Lightsail**.
3. Set the region at the top right to **Singapore**.

> If Lightsail shows a permissions error, the sandbox does not allow it — ask the
> sandbox admin before going further.

## 2. Create the server

1. **Create instance**.
2. Platform **Linux/Unix** → Blueprint **OS Only** → **Ubuntu 24.04 LTS**.
3. Plan: **$7/month (1 GB RAM)**.
4. Name it `forma` → **Create instance**. Wait for **Running** (about a minute).
5. Open the instance → **Networking** tab → **Attach static IP** → create one.
   Write the IP down — this is your site's address.

Port 80 (web) is open by default.

## 3. Open the server's terminal

On the instance page, click **Connect using SSH**. A terminal opens in your browser.

## 4. Install FORMA

Paste these into that terminal, one line at a time:

```bash
curl -fsSLO https://raw.githubusercontent.com/shaogjintan/design-inspiration-agent/live/deploy/lightsail.sh
sudo bash lightsail.sh install live
```

It takes 2–4 minutes and ends with `Open: http://<your-ip>/`.

## 5. Add the model keys

```bash
sudo nano /opt/forma/.env
```

1. Fill in `SOCLAAS_BASE_URL=`, `SOCLAAS_API_KEY=` and `SOCLAAS_MODEL=` with the same
   values as your local `.env`. (`FLASK_SECRET_KEY` is already filled in for you.)
2. Save and exit: **Ctrl+O**, **Enter**, **Ctrl+X**.
3. Restart the app:

   ```bash
   sudo systemctl restart forma
   ```

## 6. Check it works

1. Open `http://<your-ip>/` on your laptop and your phone.
2. The footer should say **"Powered by Qwen3.8 27B"**. If it says **"Demo mode"**, the
   keys are not in yet — recheck step 5.
3. Run one project end to end, from floor plan to brief.

---

## Putting a new version live

On your laptop, commit and push, then move the tag:

```bash
git tag -f live
git push -f origin live
```

On the server:

```bash
sudo bash lightsail.sh update live
```

It backs up saved projects first, then switches the code and restarts — about 20
seconds. Saved projects, uploads and learned furniture sizes are kept.

## Everyday commands (on the server)

| Command | What it does |
| --- | --- |
| `sudo bash lightsail.sh status` | Is it running, and which version is live |
| `sudo bash lightsail.sh logs` | The last 100 log lines — first place to look if something breaks |
| `sudo bash lightsail.sh backup` | Saves projects, uploads and furniture sizes to `~/forma-backups/` |

## Before the sandbox lease ends

**Everything on the server is deleted when the lease expires.**

1. On the server: `sudo bash lightsail.sh backup`
2. Download the file: in the browser terminal's **⋮** menu → **Download file** →
   `forma-backups/forma-<date>.tgz`. (Or from your laptop:
   `scp -i <key.pem> ubuntu@<ip>:~/forma-backups/*.tgz .`)

On a new lease, repeat steps 2–6. To bring saved projects back, upload the backup to
the new server and run:

```bash
sudo tar -xzf forma-<date>.tgz -C /opt/forma
sudo chown -R forma:forma /opt/forma
sudo systemctl restart forma
```

---

## If something goes wrong

| Problem | Fix |
| --- | --- |
| The page does not load at all | `sudo bash lightsail.sh status` — both `forma` and `nginx` should say *active (running)*. If not, `sudo bash lightsail.sh logs`. |
| The footer says "Demo mode" | The model keys are missing or wrong: redo step 5 and restart. |
| "502 Bad Gateway" | The app is starting or has stopped: wait 10 seconds and reload; if it stays, check the logs. |
| Uploading a big floor plan fails | Files up to 50 MB are accepted; anything larger needs resizing first. |
| The site shows an old version | Check `sudo bash lightsail.sh status` shows the commit you expect; if not, re-tag `live` on your laptop, push, and run `update live` again. |

## Optional: your own domain with HTTPS

1. At your domain registrar, add an **A record** pointing to the static IP.
2. In Lightsail → **Networking** → add a firewall rule for **HTTPS (443)**.
3. On the server:

   ```bash
   sudo bash lightsail.sh install live forma.example.com you@example.com
   ```

   This adds a free certificate and redirects `http` to `https`.

## Good to know

- **Why one worker:** the app runs as one process with 8 threads on purpose. The
  progress bar on page 5 and the floor-plan reading keep their state in memory, and a
  second process would not see it.
- **Slow pages are expected:** reading a plan and writing the brief take a minute or
  two. The server waits up to 5 minutes before giving up.
- **Your keys stay private:** `.env` is never in git. The only copy on the server is
  `/opt/forma/.env`, readable by the app alone.
- **Private repository?** The script downloads over HTTPS because the repository is
  public. If it is ever made private, install with
  `sudo REPO_URL=git@github.com:shaogjintan/design-inspiration-agent.git bash lightsail.sh install live`
  and the script will walk you through adding a read-only deploy key.
