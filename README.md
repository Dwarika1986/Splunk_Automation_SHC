## Splunk SHC Automation Web App

This project provides a small web UI + backend to:

- Upload an SSH PEM key
- Provide host IPs for `deployer`, `sh1`, `sh2`, `sh3`
- Install Splunk Enterprise 10.0.0 under `/opt` on those Linux hosts
- Configure a Search Head Cluster with 3 members and 1 deployer
- Optionally force `sh1` to become captain
- Create/deploy an app folder via the deployer to all members

### Prereqs

- Windows machine running this app
- Network access to your Linux hosts over SSH (port 22)
- A user that can `sudo` on those hosts
- Python available via `py`

### Install

```bash
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
```

### Run

```bash
py ui.py
```

Then open:

- Local: `http://127.0.0.1:5000`
- From other PCs on same network: `http://<YOUR_WINDOWS_IP>:5000`

To change bind host/port:

```bash
set APP_HOST=0.0.0.0
set APP_PORT=5000
set APP_DEBUG=0
py ui.py
```

### Sharing with others (LAN)

- Ensure Windows Firewall allows inbound TCP on your chosen port (default 5000)
- Share your Windows machine IP (for example from `ipconfig`)
- Anyone on the same network can open the URL in a browser

### Streamlit?

Streamlit can also work, but it is still a web server you run on your machine. Others would open:
`http://<YOUR_WINDOWS_IP>:8501` (default Streamlit port).

### Notes / Assumptions

- Splunk tarball is downloaded on the remote host from:
  `https://download.splunk.com/products/splunk/releases/10.0.0/linux/splunk-10.0.0-e8eb0c4654f8-linux-amd64.tgz`
- Splunk is installed to `/opt/splunk`
- Admin password and SHC secret are provided in the UI
