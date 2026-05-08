from __future__ import annotations

import os

import streamlit as st

import backend


st.set_page_config(page_title="Splunk SHC Automation", layout="wide")
st.title("Splunk Search Head Clustering Automation")

upload_dir = backend.ensure_upload_dir()

tab1, tab2 = st.tabs(["Deploy SH Cluster", "Deploy App"])

with tab1:
    st.subheader("Deploy SH Cluster (3 SH + 1 Deployer)")
    col1, col2 = st.columns(2)

    with col1:
        pem = st.file_uploader("SSH PEM key", type=["pem", "key"], key="pem_deploy")
        username = st.text_input("SSH username", placeholder="ec2-user / ubuntu / splunkadmin", key="username_deploy")
        splunk_admin_password = st.text_input("Splunk admin password", type="password", key="splunk_pw_deploy")
        shc_secret = st.text_input("SHC secret (optional)", placeholder="leave blank to auto-generate", key="shc_secret")
        force_sh1_captain = st.checkbox("Force sh1 to become captain", value=True, key="force_captain")

    with col2:
        deployer_ip = st.text_input("Deployer IP", key="deployer_ip")
        sh1_ip = st.text_input("SH1 IP", key="sh1_ip")
        sh2_ip = st.text_input("SH2 IP", key="sh2_ip")
        sh3_ip = st.text_input("SH3 IP", key="sh3_ip")

    if st.button("Deploy SH Cluster", type="primary"):
        if pem is None:
            st.error("Please upload a PEM key.")
        elif not (username and deployer_ip and sh1_ip and sh2_ip and sh3_ip and splunk_admin_password):
            st.error("Please fill all required fields.")
        else:
            pem_path = os.path.join(upload_dir, pem.name)
            with open(pem_path, "wb") as f:
                f.write(pem.getbuffer())
            job = backend.start_deploy_job(
                pem_path=pem_path,
                username=username.strip(),
                deployer_ip=deployer_ip.strip(),
                sh1_ip=sh1_ip.strip(),
                sh2_ip=sh2_ip.strip(),
                sh3_ip=sh3_ip.strip(),
                splunk_admin_password=splunk_admin_password.strip(),
                shc_secret=shc_secret.strip(),
                force_sh1_captain=force_sh1_captain,
            )
            st.success(f"Started job: {job.id}")
            st.session_state["last_job_id"] = job.id

with tab2:
    st.subheader("Deploy App via Deployer")
    col1, col2 = st.columns(2)
    with col1:
        pem_app = st.file_uploader("SSH PEM key", type=["pem", "key"], key="pem_app")
        username_app = st.text_input("SSH username", key="username_app")
        splunk_admin_password_app = st.text_input("Splunk admin password", type="password", key="splunk_pw_app")
    with col2:
        deployer_ip_app = st.text_input("Deployer IP", key="deployer_ip_app")
        captain_ip_app = st.text_input("Captain IP (usually sh1)", key="captain_ip_app")
        app_folder_name = st.text_input("App folder name", placeholder="my_custom_app", key="app_folder")

    if st.button("Deploy App", type="primary"):
        if pem_app is None:
            st.error("Please upload a PEM key.")
        elif not (username_app and deployer_ip_app and captain_ip_app and splunk_admin_password_app and app_folder_name):
            st.error("Please fill all required fields.")
        else:
            pem_path = os.path.join(upload_dir, pem_app.name)
            with open(pem_path, "wb") as f:
                f.write(pem_app.getbuffer())
            job = backend.start_deploy_app_job(
                pem_path=pem_path,
                username=username_app.strip(),
                deployer_ip=deployer_ip_app.strip(),
                captain_ip=captain_ip_app.strip(),
                splunk_admin_password=splunk_admin_password_app.strip(),
                app_folder_name=app_folder_name.strip(),
            )
            st.success(f"Started job: {job.id}")
            st.session_state["last_job_id"] = job.id

st.divider()
st.subheader("Job status")
job_id = st.text_input("Job ID", value=st.session_state.get("last_job_id", ""), key="job_id")
if job_id:
    job = backend.get_job(job_id.strip())
    if job is None:
        st.warning("Job not found.")
    else:
        st.write({"status": job.status, "kind": job.kind, "error": job.error, "result": job.result})
        st.text_area("Logs", value="\n".join(job.logs[-300:]), height=350)
        if job.status in ("running", "queued"):
            st.caption("Auto-refreshing while job runs…")
            st.rerun()
